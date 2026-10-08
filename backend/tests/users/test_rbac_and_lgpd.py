import pytest

from apps.audit.models import AuditLog
from apps.users import rbac
from apps.users.models import Consent, Role, User
from tests.conftest import PASSWORD

ME = "/api/v1/me/"


class TestPermissionMatrix:
    """The RBAC matrix is part of the contract: changing it must break a test on purpose."""

    @pytest.mark.parametrize(
        ("role", "permission", "allowed"),
        [
            (Role.CUSTOMER, rbac.AUDIT_VIEW, False),
            (Role.MERCHANT_OWNER, rbac.AUDIT_VIEW, False),
            (Role.MERCHANT_OWNER, rbac.USERS_VIEW, False),
            (Role.MODERATOR, rbac.USERS_VIEW, True),
            (Role.MODERATOR, rbac.AUDIT_VIEW, False),
            (Role.SUPPORT, rbac.USERS_VIEW, True),
            (Role.SUPPORT, rbac.USERS_CHANGE_ROLE, False),
            (Role.ADMIN, rbac.AUDIT_VIEW, True),
            (Role.ADMIN, rbac.USERS_CHANGE_ROLE, False),
            (Role.SUPERADMIN, rbac.USERS_CHANGE_ROLE, True),
            (Role.SUPERADMIN, rbac.AUDIT_VIEW, True),
        ],
    )
    def test_matrix(self, role, permission, allowed):
        user = User(role=role, is_active=True)
        assert rbac.has_permission(user, permission) is allowed

    def test_every_role_is_mapped(self):
        assert set(Role.values) == set(rbac.ROLE_PERMISSIONS)

    def test_inactive_user_has_no_permissions(self):
        assert (
            rbac.has_permission(User(role=Role.SUPERADMIN, is_active=False), rbac.AUDIT_VIEW)
            is False
        )


@pytest.mark.django_db
class TestRoleEndpoints:
    def test_customer_cannot_escalate_via_profile(self, make_user, login_as):
        user = make_user()
        client = login_as(user)
        client.patch(ME, {"role": "SUPERADMIN", "email": "x@example.com"}, format="json")
        user.refresh_from_db()
        assert user.role == Role.CUSTOMER
        assert user.email != "x@example.com"

    def test_customer_cannot_change_roles(self, make_user, login_as):
        target = make_user()
        client = login_as(make_user())
        response = client.patch(
            f"/api/v1/users/{target.pk}/role/", {"role": "ADMIN"}, format="json"
        )
        assert response.status_code == 403

    def test_admin_cannot_change_roles(self, make_user, login_as):
        target = make_user()
        client = login_as(make_user(role=Role.ADMIN))
        response = client.patch(
            f"/api/v1/users/{target.pk}/role/", {"role": "ADMIN"}, format="json"
        )
        assert response.status_code == 403

    def test_superadmin_changes_role_and_it_is_audited(self, make_user, login_as):
        target = make_user()
        admin = make_user(role=Role.SUPERADMIN)
        client = login_as(admin)
        response = client.patch(
            f"/api/v1/users/{target.pk}/role/", {"role": "MODERATOR"}, format="json"
        )
        assert response.status_code == 200
        target.refresh_from_db()
        assert target.role == Role.MODERATOR
        entry = AuditLog.objects.get(action="user.role_changed")
        assert entry.actor == admin
        assert entry.previous_value == {"role": "CUSTOMER"}
        assert entry.new_value == {"role": "MODERATOR"}

    def test_superadmin_cannot_change_own_role(self, make_user, login_as):
        admin = make_user(role=Role.SUPERADMIN)
        client = login_as(admin)
        response = client.patch(
            f"/api/v1/users/{admin.pk}/role/", {"role": "CUSTOMER"}, format="json"
        )
        assert response.status_code == 403

    def test_invalid_role_is_rejected(self, make_user, login_as):
        target = make_user()
        client = login_as(make_user(role=Role.SUPERADMIN))
        response = client.patch(f"/api/v1/users/{target.pk}/role/", {"role": "GOD"}, format="json")
        assert response.status_code == 400

    def test_audit_endpoint_requires_permission(self, make_user, login_as):
        assert login_as(make_user()).get("/api/v1/audit/logs/").status_code == 403

    def test_admin_reads_audit_without_ip(self, make_user, login_as):
        client = login_as(make_user(role=Role.ADMIN))
        response = client.get("/api/v1/audit/logs/")
        assert response.status_code == 200
        assert response.data["results"]
        assert "ip_address" not in response.data["results"][0]


@pytest.mark.django_db
class TestConsents:
    def test_current_consent_is_latest_row_and_history_is_kept(self, make_user, login_as):
        user = make_user()
        client = login_as(user)
        client.post("/api/v1/me/consents/", {"purpose": "LOCATION", "granted": True}, format="json")
        client.post(
            "/api/v1/me/consents/", {"purpose": "LOCATION", "granted": False}, format="json"
        )
        listing = {c["purpose"]: c["granted"] for c in client.get("/api/v1/me/consents/").json()}
        assert listing["LOCATION"] is False
        assert Consent.objects.filter(user=user, purpose="LOCATION").count() == 2

    def test_unknown_purpose_is_rejected(self, make_user, login_as):
        client = login_as(make_user())
        response = client.post(
            "/api/v1/me/consents/", {"purpose": "SELL_DATA", "granted": True}, format="json"
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestLgpdRights:
    def test_export_contains_only_own_data(self, make_user, login_as):
        me = make_user(email="me@example.com", display_name="Eu")
        other = make_user(email="other@example.com")
        client = login_as(me)
        data = client.get("/api/v1/me/export/").json()
        assert data["profile"]["email"] == "me@example.com"
        assert "other@example.com" not in str(data)
        assert str(other.pk) not in str(data)

    def test_correction_updates_display_name(self, make_user, login_as):
        user = make_user()
        client = login_as(user)
        client.patch(ME, {"display_name": "Novo Nome"}, format="json")
        user.refresh_from_db()
        assert user.display_name == "Novo Nome"

    def test_delete_requires_correct_password(self, make_user, login_as):
        user = make_user()
        client = login_as(user)
        assert client.delete(ME, {"password": "errada"}, format="json").status_code == 403
        user.refresh_from_db()
        assert user.is_active and user.anonymized_at is None

    def test_delete_anonymizes_and_blocks_login(self, make_user, login_as, api):
        user = make_user(email="sai@example.com", display_name="Sai")
        pk = user.pk
        client = login_as(user)
        assert client.delete(ME, {"password": PASSWORD}, format="json").status_code == 204
        user = User.objects.get(pk=pk)
        assert user.email == f"deleted-{pk}@deleted.invalid"
        assert user.display_name == ""
        assert user.anonymized_at is not None
        assert not user.has_usable_password()
        api.credentials()
        assert (
            api.post(
                "/api/v1/auth/login/", {"email": "sai@example.com", "password": PASSWORD}
            ).status_code
            == 401
        )
        assert AuditLog.objects.filter(action="user.deleted", entity_id=str(pk)).exists()
        # Consent rows are kept as proof of consent; they hold no personal data once anonymized.
        assert Consent.objects.filter(user=user).exists() is False  # none were created here

    def test_delete_revokes_existing_refresh_tokens(self, make_user, api):
        user = make_user()
        tokens = api.post("/api/v1/auth/login/", {"email": user.email, "password": PASSWORD}).data
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        api.delete(ME, {"password": PASSWORD}, format="json")
        api.credentials()
        assert api.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}).status_code == 401
