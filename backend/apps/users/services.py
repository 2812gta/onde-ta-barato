"""Use cases for accounts. Views stay thin; rules live here."""

import hashlib
from typing import Any

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit import services as audit

from .models import Consent, ConsentPurpose, Role, User

POLICY_VERSION = "2026-10-draft"  # bump whenever TERMS/PRIVACY text changes
_VERIFY_SALT = "users.email-verification"


class AccountLocked(Exception):
    """Too many failed logins for this e-mail."""


class InvalidCredentials(Exception):
    """Wrong e-mail or password, or inactive account. Deliberately non-specific."""


class InvalidToken(Exception):
    """Verification or reset token is invalid or expired."""


# --- Registration -----------------------------------------------------------


@transaction.atomic
def register_user(
    *, email: str, password: str, display_name: str = "", request: HttpRequest | None = None
) -> User | None:
    """Create a CUSTOMER. If the e-mail exists, notify the owner and return None.

    The caller gets the same response either way, so the endpoint does not reveal
    which e-mails are registered.
    """
    email = email.strip().lower()
    if User.objects.filter(email=email).exists():
        send_mail(
            "Tentativa de cadastro com seu e-mail",
            "Alguém tentou criar uma conta com este e-mail, que já está cadastrado. "
            "Se foi você, use 'Esqueci minha senha'. Caso contrário, ignore esta mensagem.",
            settings.DEFAULT_FROM_EMAIL,
            [email],
        )
        return None
    user = User.objects.create_user(email=email, password=password, display_name=display_name)
    for purpose in (ConsentPurpose.TERMS, ConsentPurpose.PRIVACY_POLICY):
        Consent.objects.create(
            user=user, purpose=purpose, granted=True, policy_version=POLICY_VERSION
        )
    audit.record(
        "user.registered", actor=user, entity_type="user", entity_id=user.pk, request=request
    )
    send_verification_email(user)
    return user


def validate_new_password(password: str, user: User | None = None) -> None:
    validate_password(password, user)


# --- Login / lockout --------------------------------------------------------


def _lock_key(email: str) -> str:
    return "login-fail:" + hashlib.sha256(email.strip().lower().encode()).hexdigest()


def login(*, email: str, password: str, request: HttpRequest | None = None) -> dict[str, str]:
    key = _lock_key(email)
    if cache.get(key, 0) >= settings.LOGIN_MAX_FAILURES:
        audit.record(
            "user.login_locked", entity_type="user", request=request, metadata={"reason": "lockout"}
        )
        raise AccountLocked
    user = authenticate(request=request, username=email.strip().lower(), password=password)
    if user is None or not user.is_active or user.anonymized_at is not None:
        cache.set(key, cache.get(key, 0) + 1, settings.LOGIN_LOCKOUT_SECONDS)
        audit.record("user.login_failed", entity_type="user", request=request)
        raise InvalidCredentials
    cache.delete(key)
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    audit.record("user.login", actor=user, entity_type="user", entity_id=user.pk, request=request)
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


# --- E-mail verification ----------------------------------------------------


def send_verification_email(user: User) -> None:
    token = signing.dumps({"uid": str(user.pk), "email": user.email}, salt=_VERIFY_SALT)
    send_mail(
        "Confirme seu e-mail - OndeTáBarato",
        f"Código de confirmação (válido por 48 horas):\n{token}",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )


def verify_email(token: str) -> User:
    try:
        data = signing.loads(
            token, salt=_VERIFY_SALT, max_age=settings.EMAIL_VERIFICATION_MAX_AGE_SECONDS
        )
        user = User.objects.get(pk=data["uid"], email=data["email"])
    except (signing.BadSignature, User.DoesNotExist, KeyError, ValueError) as exc:
        raise InvalidToken from exc
    if user.email_verified_at is None:
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])
        audit.record("user.email_verified", actor=user, entity_type="user", entity_id=user.pk)
    return user


def resend_verification(user: User) -> None:
    if not user.is_email_verified:
        send_verification_email(user)


# --- Password reset ---------------------------------------------------------


def request_password_reset(email: str) -> None:
    """Always silent about whether the e-mail exists."""
    user = User.objects.filter(
        email=email.strip().lower(), is_active=True, anonymized_at__isnull=True
    ).first()
    if user is None:
        return
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    send_mail(
        "Redefinição de senha - OndeTáBarato",
        f"Código para redefinir sua senha (válido por 1 hora):\n{uid}.{token}",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )
    audit.record("user.password_reset_requested", actor=user, entity_type="user", entity_id=user.pk)


def confirm_password_reset(*, code: str, new_password: str) -> User:
    try:
        uid, token = code.split(".", 1)
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
    except (ValueError, User.DoesNotExist, TypeError, UnicodeDecodeError) as exc:
        raise InvalidToken from exc
    if not default_token_generator.check_token(user, token):
        raise InvalidToken
    validate_new_password(new_password, user)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    revoke_all_tokens(user)
    cache.delete(_lock_key(user.email))
    audit.record("user.password_reset", actor=user, entity_type="user", entity_id=user.pk)
    return user


def revoke_all_tokens(user: User) -> None:
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    for outstanding in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=outstanding)


# --- Consent ----------------------------------------------------------------


def set_consent(
    *, user: User, purpose: str, granted: bool, request: HttpRequest | None = None
) -> Consent:
    consent = Consent.objects.create(
        user=user, purpose=purpose, granted=granted, policy_version=POLICY_VERSION
    )
    audit.record(
        "consent.changed",
        actor=user,
        entity_type="consent",
        entity_id=consent.pk,
        new_value={"purpose": purpose, "granted": granted},
        request=request,
    )
    return consent


def current_consents(user: User) -> dict[str, Consent]:
    latest: dict[str, Consent] = {}
    for consent in user.consents.order_by("created_at"):
        latest[consent.purpose] = consent
    return latest


# --- LGPD: export and deletion ---------------------------------------------


def export_user_data(user: User) -> dict[str, Any]:
    return {
        "exported_at": timezone.now().isoformat(),
        "profile": {
            "id": str(user.pk),
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "email_verified_at": (
                user.email_verified_at.isoformat() if user.email_verified_at else None
            ),
            "created_at": user.created_at.isoformat(),
        },
        "consents": [
            {
                "purpose": c.purpose,
                "granted": c.granted,
                "policy_version": c.policy_version,
                "at": c.created_at.isoformat(),
            }
            for c in user.consents.order_by("created_at")
        ],
        "shopping_lists": [
            {
                "name": shopping_list.name,
                "items": [
                    {"product": i.product_variant.product.name, "quantity": str(i.quantity)}
                    for i in shopping_list.items.select_related("product_variant__product")
                ],
            }
            for shopping_list in user.shopping_lists.all()
        ],
        "contributions": [
            {
                "store": c.store.name,
                "status": c.status,
                "corrected": c.corrected,
                "at": c.created_at.isoformat(),
            }
            for c in user.contributions.select_related("store").order_by("created_at")
        ],
        "activity": [
            {"action": a.action, "entity_type": a.entity_type, "at": a.created_at.isoformat()}
            for a in user.audit_logs.order_by("created_at")
        ],
    }


@transaction.atomic
def delete_account(*, user: User, password: str, request: HttpRequest | None = None) -> None:
    """Anonymize the account. Rows are kept so history stays consistent, minus personal data."""
    if not user.check_password(password):
        raise InvalidCredentials
    revoke_all_tokens(user)
    # Shopping habits are personal data with no history value: erased, not anonymized.
    user.shopping_lists.all().delete()
    user.shopping_carts.all().delete()
    # Photos still waiting for confirmation are personal data: deleted now, not at expiry.
    from apps.contributions.services import discard_open_drafts

    discard_open_drafts(user)
    audit.record("user.deleted", actor=user, entity_type="user", entity_id=user.pk, request=request)
    user.email = f"deleted-{user.pk}@deleted.invalid"
    user.display_name = ""
    user.is_active = False
    user.role = Role.CUSTOMER
    user.is_staff = False
    user.is_superuser = False
    user.anonymized_at = timezone.now()
    user.set_unusable_password()
    user.save()
    # Consent rows are kept on purpose: proof of consent is retained without personal data.


# --- Roles ------------------------------------------------------------------


@transaction.atomic
def change_role(
    *, actor: User, target: User, new_role: str, request: HttpRequest | None = None
) -> User:
    previous = target.role
    target.role = new_role
    target.is_staff = new_role in {Role.ADMIN, Role.SUPERADMIN}
    target.is_superuser = new_role == Role.SUPERADMIN
    target.save(update_fields=["role", "is_staff", "is_superuser"])
    audit.record(
        "user.role_changed",
        actor=actor,
        entity_type="user",
        entity_id=target.pk,
        previous_value={"role": previous},
        new_value={"role": new_role},
        request=request,
    )
    return target
