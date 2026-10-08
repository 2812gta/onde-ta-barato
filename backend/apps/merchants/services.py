"""Merchant use cases. Verification is manual in the MVP: there is no automatic
CNPJ/Receita Federal lookup, and none is implied to exist."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.core.validators import normalize_cnpj
from apps.users import rbac
from apps.users.models import Role, User

from .models import (
    MemberRole,
    Merchant,
    MerchantMembership,
    MerchantVerification,
    VerificationStatus,
)

S = VerificationStatus

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    S.PENDING: {S.UNDER_REVIEW},
    S.UNDER_REVIEW: {S.VERIFIED, S.REJECTED},
    S.REJECTED: {S.PENDING},
    S.VERIFIED: {S.SUSPENDED},
    S.SUSPENDED: {S.VERIFIED},
}

MANAGE_ROLES = {MemberRole.OWNER, MemberRole.MANAGER}
PUBLISH_ROLES = {MemberRole.OWNER, MemberRole.MANAGER, MemberRole.OPERATOR}


def membership_role(user: User, merchant: Merchant) -> str | None:
    if not getattr(user, "is_authenticated", False):
        return None
    return (
        MerchantMembership.objects.filter(user=user, merchant=merchant)
        .values_list("role", flat=True)
        .first()
    )


def can_manage(user: User, merchant: Merchant) -> bool:
    return membership_role(user, merchant) in MANAGE_ROLES


def can_publish(user: User, merchant: Merchant) -> bool:
    return membership_role(user, merchant) in PUBLISH_ROLES


def _promote_global_role(user: User, role: str) -> None:
    """A consumer who joins a merchant gets the matching global role (never downgrades staff)."""
    if user.role == Role.CUSTOMER:
        user.role = role
        user.save(update_fields=["role"])


@transaction.atomic
def create_merchant(
    *,
    owner: User,
    legal_name: str,
    trade_name: str,
    cnpj: str = "",
    contact_email: str = "",
    contact_phone: str = "",
) -> Merchant:
    normalized = normalize_cnpj(cnpj) if cnpj else None
    if normalized and Merchant.objects.filter(cnpj=normalized).exists():
        raise ValidationError("Já existe um comerciante com este CNPJ.")
    merchant = Merchant.objects.create(
        legal_name=legal_name.strip(),
        trade_name=trade_name.strip(),
        cnpj=normalized,
        contact_email=contact_email,
        contact_phone=contact_phone,
    )
    MerchantMembership.objects.create(merchant=merchant, user=owner, role=MemberRole.OWNER)
    _promote_global_role(owner, Role.MERCHANT_OWNER)
    audit.record(
        "merchant.created",
        actor=owner,
        entity_type="merchant",
        entity_id=merchant.pk,
        new_value={"trade_name": merchant.trade_name, "status": merchant.status},
    )
    return merchant


def _authorize_transition(actor: User, merchant: Merchant, target: str) -> None:
    current = merchant.status
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValidationError(f"Transição inválida: {current} -> {target}.")
    if (current, target) in {(S.PENDING, S.UNDER_REVIEW), (S.REJECTED, S.PENDING)}:
        allowed = membership_role(actor, merchant) == MemberRole.OWNER
    elif target in {S.VERIFIED, S.REJECTED} and current == S.UNDER_REVIEW:
        allowed = rbac.has_permission(actor, rbac.MERCHANTS_REVIEW)
    else:  # suspend / reinstate
        allowed = rbac.has_permission(actor, rbac.MERCHANTS_SUSPEND)
    if not allowed:
        raise PermissionDenied("Você não pode executar esta transição.")


@transaction.atomic
def transition(*, merchant: Merchant, to_status: str, actor: User, notes: str = "") -> Merchant:
    _authorize_transition(actor, merchant, to_status)
    if to_status in {S.REJECTED, S.SUSPENDED} and not notes.strip():
        raise ValidationError("Informe a justificativa.")
    previous = merchant.status
    merchant.status = to_status
    if to_status == S.VERIFIED:
        merchant.verified_at = timezone.now()
    elif to_status == S.SUSPENDED:
        merchant.verified_at = None
    merchant.save(update_fields=["status", "verified_at", "updated_at"])
    MerchantVerification.objects.create(
        merchant=merchant, from_status=previous, to_status=to_status, actor=actor, notes=notes
    )
    audit.record(
        "merchant.status_changed",
        actor=actor,
        entity_type="merchant",
        entity_id=merchant.pk,
        previous_value={"status": previous},
        new_value={"status": to_status},
        metadata={"has_notes": bool(notes.strip())},
    )
    return merchant


@transaction.atomic
def add_member(*, merchant: Merchant, actor: User, email: str, role: str) -> MerchantMembership:
    if membership_role(actor, merchant) != MemberRole.OWNER:
        raise PermissionDenied("Apenas o proprietário gerencia a equipe.")
    if role not in {MemberRole.MANAGER, MemberRole.OPERATOR}:
        raise ValidationError("Papel inválido para membro da equipe.")
    user = User.objects.filter(
        email=email.strip().lower(), is_active=True, anonymized_at__isnull=True
    ).first()
    if user is None:
        raise ValidationError("Usuário não encontrado. Peça que ele crie uma conta primeiro.")
    membership, created = MerchantMembership.objects.get_or_create(
        merchant=merchant, user=user, defaults={"role": role}
    )
    if not created and membership.role == MemberRole.OWNER:
        raise ValidationError("O proprietário não pode ter o papel alterado.")
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])
    _promote_global_role(user, role)
    audit.record(
        "merchant.member_added",
        actor=actor,
        entity_type="merchant",
        entity_id=merchant.pk,
        new_value={"user_id": str(user.pk), "role": role},
    )
    return membership


@transaction.atomic
def remove_member(*, merchant: Merchant, actor: User, user_id: str) -> None:
    if membership_role(actor, merchant) != MemberRole.OWNER:
        raise PermissionDenied("Apenas o proprietário gerencia a equipe.")
    membership = MerchantMembership.objects.filter(merchant=merchant, user_id=user_id).first()
    if membership is None:
        raise ValidationError("Membro não encontrado.")
    if membership.role == MemberRole.OWNER:
        raise ValidationError("O proprietário não pode ser removido.")
    membership.delete()
    audit.record(
        "merchant.member_removed",
        actor=actor,
        entity_type="merchant",
        entity_id=merchant.pk,
        previous_value={"user_id": str(user_id), "role": membership.role},
    )
