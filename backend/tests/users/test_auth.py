import pytest
from django.core import mail
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from apps.audit.models import AuditLog
from apps.users.models import Consent, Role, User
from tests.conftest import PASSWORD

REGISTER = "/api/v1/auth/register/"
LOGIN = "/api/v1/auth/login/"


def register(api, email="novo@example.com", **extra):
    payload = {"email": email, "password": PASSWORD, "accept_terms": True, **extra}
    return api.post(REGISTER, payload)


@pytest.mark.django_db
class TestRegistration:
    def test_creates_customer_with_consents_and_sends_verification(self, api):
        response = register(api, display_name="Ana")
        assert response.status_code == 201
        user = User.objects.get(email="novo@example.com")
        assert user.role == Role.CUSTOMER
        assert user.check_password(PASSWORD)
        assert user.password.startswith(("argon2", "md5"))  # md5 only in test settings
        assert set(Consent.objects.filter(user=user).values_list("purpose", flat=True)) == {
            "TERMS",
            "PRIVACY_POLICY",
        }
        assert len(mail.outbox) == 1
        assert AuditLog.objects.filter(action="user.registered").count() == 1

    def test_requires_accepting_terms(self, api):
        response = api.post(
            REGISTER, {"email": "a@example.com", "password": PASSWORD, "accept_terms": False}
        )
        assert response.status_code == 400
        assert not User.objects.filter(email="a@example.com").exists()

    def test_rejects_weak_password(self, api):
        response = api.post(
            REGISTER, {"email": "a@example.com", "password": "12345678", "accept_terms": True}
        )
        assert response.status_code == 400

    def test_cannot_register_as_privileged_role(self, api):
        response = register(api, role="SUPERADMIN", is_staff=True)
        assert response.status_code == 201
        assert User.objects.get(email="novo@example.com").role == Role.CUSTOMER

    def test_duplicate_email_does_not_reveal_existence(self, api, make_user):
        make_user(email="dup@example.com")
        first = register(api, email="novo2@example.com")
        second = register(api, email="dup@example.com")
        assert first.status_code == second.status_code == 201
        assert first.json() == second.json()
        assert User.objects.filter(email="dup@example.com").count() == 1

    def test_email_is_case_insensitive(self, api, make_user):
        make_user(email="case@example.com")
        register(api, email="CASE@Example.com")
        assert User.objects.filter(email__iexact="case@example.com").count() == 1


@pytest.mark.django_db
class TestLogin:
    def test_success_returns_tokens(self, api, make_user):
        user = make_user()
        response = api.post(LOGIN, {"email": user.email, "password": PASSWORD})
        assert response.status_code == 200
        assert set(response.data) == {"access", "refresh"}
        assert AuditLog.objects.filter(action="user.login", actor=user).exists()

    def test_wrong_password_and_unknown_user_look_identical(self, api, make_user):
        user = make_user()
        wrong = api.post(LOGIN, {"email": user.email, "password": "errada-errada-1"})
        unknown = api.post(LOGIN, {"email": "ninguem@example.com", "password": "errada-errada-1"})
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json()

    def test_lockout_after_repeated_failures(self, api, make_user, settings):
        user = make_user()
        for _ in range(settings.LOGIN_MAX_FAILURES):
            assert (
                api.post(LOGIN, {"email": user.email, "password": "errada-errada-1"}).status_code
                == 401
            )
        # Even the correct password is refused while locked.
        locked = api.post(LOGIN, {"email": user.email, "password": PASSWORD})
        assert locked.status_code == 429

    def test_success_resets_failure_counter(self, api, make_user, settings):
        user = make_user()
        for _ in range(settings.LOGIN_MAX_FAILURES - 1):
            api.post(LOGIN, {"email": user.email, "password": "errada-errada-1"})
        assert api.post(LOGIN, {"email": user.email, "password": PASSWORD}).status_code == 200
        for _ in range(settings.LOGIN_MAX_FAILURES - 1):
            api.post(LOGIN, {"email": user.email, "password": "errada-errada-1"})
        assert api.post(LOGIN, {"email": user.email, "password": PASSWORD}).status_code == 200

    def test_inactive_user_cannot_login(self, api, make_user):
        user = make_user(is_active=False)
        assert api.post(LOGIN, {"email": user.email, "password": PASSWORD}).status_code == 401

    def test_throttle_scope_limits_requests(self, api, make_user, monkeypatch):
        user = make_user()
        monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"login": "2/min"})
        codes = [
            api.post(LOGIN, {"email": user.email, "password": PASSWORD}).status_code
            for _ in range(3)
        ]
        assert codes == [200, 200, 429]


@pytest.mark.django_db
class TestTokens:
    def test_refresh_rotates_and_blacklists_old_token(self, api, make_user):
        user = make_user()
        tokens = api.post(LOGIN, {"email": user.email, "password": PASSWORD}).data
        rotated = api.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]})
        assert rotated.status_code == 200
        assert rotated.data["refresh"] != tokens["refresh"]
        reuse = api.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]})
        assert reuse.status_code == 401

    def test_logout_revokes_refresh_token(self, api, make_user):
        user = make_user()
        tokens = api.post(LOGIN, {"email": user.email, "password": PASSWORD}).data
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        assert api.post("/api/v1/auth/logout/", {"refresh": tokens["refresh"]}).status_code == 204
        assert BlacklistedToken.objects.count() == 1
        api.credentials()
        assert api.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}).status_code == 401

    def test_protected_endpoint_requires_token(self, api, db):
        assert api.get("/api/v1/me/").status_code == 401

    def test_garbage_token_is_rejected(self, api, db):
        api.credentials(HTTP_AUTHORIZATION="Bearer not-a-jwt")
        assert api.get("/api/v1/me/").status_code == 401


@pytest.mark.django_db
class TestEmailVerification:
    def _token_from_mail(self):
        return mail.outbox[-1].body.strip().splitlines()[-1]

    def test_verify_flow(self, api):
        register(api)
        token = self._token_from_mail()
        response = api.post("/api/v1/auth/verify-email/", {"token": token})
        assert response.status_code == 200
        assert User.objects.get(email="novo@example.com").is_email_verified

    def test_tampered_token_is_rejected(self, api):
        register(api)
        token = self._token_from_mail() + "x"
        assert api.post("/api/v1/auth/verify-email/", {"token": token}).status_code == 400

    def test_expired_token_is_rejected(self, api, settings):
        register(api)
        token = self._token_from_mail()
        settings.EMAIL_VERIFICATION_MAX_AGE_SECONDS = -1
        assert api.post("/api/v1/auth/verify-email/", {"token": token}).status_code == 400


@pytest.mark.django_db
class TestPasswordReset:
    def _code(self):
        return mail.outbox[-1].body.strip().splitlines()[-1]

    def test_request_is_silent_for_unknown_email(self, api):
        response = api.post("/api/v1/auth/password-reset/", {"email": "ninguem@example.com"})
        assert response.status_code == 202
        assert mail.outbox == []

    def test_full_reset_flow_revokes_sessions_and_changes_password(self, api, make_user):
        user = make_user()
        old_tokens = api.post(LOGIN, {"email": user.email, "password": PASSWORD}).data
        api.post("/api/v1/auth/password-reset/", {"email": user.email})
        code = self._code()
        new_password = "Outra-Senha-Forte-9!"
        done = api.post(
            "/api/v1/auth/password-reset/confirm/", {"code": code, "new_password": new_password}
        )
        assert done.status_code == 200
        assert api.post(LOGIN, {"email": user.email, "password": PASSWORD}).status_code == 401
        assert api.post(LOGIN, {"email": user.email, "password": new_password}).status_code == 200
        assert (
            api.post("/api/v1/auth/refresh/", {"refresh": old_tokens["refresh"]}).status_code == 401
        )

    def test_code_is_single_use(self, api, make_user):
        user = make_user()
        api.post("/api/v1/auth/password-reset/", {"email": user.email})
        code = self._code()
        body = {"code": code, "new_password": "Outra-Senha-Forte-9!"}
        assert api.post("/api/v1/auth/password-reset/confirm/", body).status_code == 200
        assert api.post("/api/v1/auth/password-reset/confirm/", body).status_code == 400

    def test_weak_new_password_is_rejected(self, api, make_user):
        user = make_user()
        api.post("/api/v1/auth/password-reset/", {"email": user.email})
        response = api.post(
            "/api/v1/auth/password-reset/confirm/",
            {"code": self._code(), "new_password": "12345678"},
        )
        assert response.status_code == 400
        assert "new_password" in response.json()

    def test_garbage_code_is_rejected(self, api, db):
        response = api.post(
            "/api/v1/auth/password-reset/confirm/",
            {"code": "abc.def", "new_password": "Outra-Senha-Forte-9!"},
        )
        assert response.status_code == 400
