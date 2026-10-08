import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.audit.models import AuditLog
from apps.core.append_only import ImmutableRecordError
from apps.merchants import services
from apps.merchants.models import Merchant, MerchantVerification, VerificationStatus
from apps.users.models import Role

VALID_CNPJ = "11.222.333/0001-81"
S = VerificationStatus


@pytest.mark.django_db
class TestCreation:
    def test_creator_becomes_owner_and_global_role_is_promoted(self, make_user, make_merchant):
        user = make_user()
        merchant = make_merchant(owner=user, cnpj=VALID_CNPJ)
        user.refresh_from_db()
        assert user.role == Role.MERCHANT_OWNER
        assert merchant.status == S.PENDING
        assert merchant.cnpj == "11222333000181"
        assert not merchant.is_verified
        assert services.membership_role(user, merchant) == "MERCHANT_OWNER"
        assert AuditLog.objects.filter(action="merchant.created").exists()

    def test_staff_role_is_never_downgraded(self, make_user, make_merchant):
        admin = make_user(role=Role.ADMIN)
        make_merchant(owner=admin)
        admin.refresh_from_db()
        assert admin.role == Role.ADMIN

    def test_invalid_cnpj_is_refused(self, make_user):
        with pytest.raises(ValidationError):
            services.create_merchant(
                owner=make_user(), legal_name="X", trade_name="X", cnpj="11222333000180"
            )

    def test_duplicate_cnpj_is_refused(self, make_merchant):
        make_merchant(cnpj=VALID_CNPJ)
        with pytest.raises(ValidationError):
            make_merchant(cnpj="11222333000181")

    def test_cnpj_is_optional_and_not_unique_when_empty(self, make_merchant):
        make_merchant()
        make_merchant()
        assert Merchant.objects.filter(cnpj__isnull=True).count() == 2


@pytest.mark.django_db
class TestVerificationWorkflow:
    @pytest.fixture
    def parties(self, make_user, make_merchant):
        owner = make_user()
        return {
            "owner": owner,
            "merchant": make_merchant(owner=owner),
            "moderator": make_user(role=Role.MODERATOR),
            "admin": make_user(role=Role.ADMIN),
            "stranger": make_user(),
        }

    def move(self, p, actor, to, notes=""):
        return services.transition(
            merchant=p["merchant"], to_status=to, actor=p[actor], notes=notes
        )

    def test_happy_path(self, parties):
        self.move(parties, "owner", S.UNDER_REVIEW)
        self.move(parties, "moderator", S.VERIFIED)
        merchant = parties["merchant"]
        assert merchant.is_verified and merchant.verified_at is not None
        history = list(
            MerchantVerification.objects.filter(merchant=merchant).order_by("created_at")
        )
        assert [(h.from_status, h.to_status) for h in history] == [
            (S.PENDING, S.UNDER_REVIEW),
            (S.UNDER_REVIEW, S.VERIFIED),
        ]

    def test_cannot_skip_review(self, parties):
        with pytest.raises(ValidationError):
            self.move(parties, "admin", S.VERIFIED)

    def test_owner_cannot_verify_themselves(self, parties):
        self.move(parties, "owner", S.UNDER_REVIEW)
        with pytest.raises(PermissionDenied):
            self.move(parties, "owner", S.VERIFIED)
        assert not parties["merchant"].is_verified

    def test_stranger_cannot_submit(self, parties):
        with pytest.raises(PermissionDenied):
            self.move(parties, "stranger", S.UNDER_REVIEW)

    def test_rejection_requires_justification_and_allows_resubmission(self, parties):
        self.move(parties, "owner", S.UNDER_REVIEW)
        with pytest.raises(ValidationError):
            self.move(parties, "moderator", S.REJECTED, notes="  ")
        self.move(parties, "moderator", S.REJECTED, notes="CNPJ não confere")
        self.move(parties, "owner", S.PENDING)
        self.move(parties, "owner", S.UNDER_REVIEW)

    def test_only_admin_suspends_and_badge_is_removed(self, parties):
        self.move(parties, "owner", S.UNDER_REVIEW)
        self.move(parties, "moderator", S.VERIFIED)
        with pytest.raises(PermissionDenied):
            self.move(parties, "moderator", S.SUSPENDED, notes="x")
        self.move(parties, "admin", S.SUSPENDED, notes="Denúncias confirmadas")
        merchant = parties["merchant"]
        assert not merchant.is_verified
        assert merchant.verified_at is None
        self.move(parties, "admin", S.VERIFIED)
        assert merchant.is_verified

    def test_transitions_are_audited_without_leaking_notes(self, parties):
        self.move(parties, "owner", S.UNDER_REVIEW)
        self.move(parties, "moderator", S.REJECTED, notes="dado interno sensível")
        entry = AuditLog.objects.filter(action="merchant.status_changed").first()
        assert "dado interno" not in str(entry.new_value) + str(entry.metadata)
        assert entry.previous_value == {"status": S.UNDER_REVIEW}

    def test_history_is_append_only(self, parties):
        self.move(parties, "owner", S.UNDER_REVIEW)
        with pytest.raises(ImmutableRecordError):
            MerchantVerification.objects.all().update(notes="x")


@pytest.mark.django_db
class TestTeam:
    def test_owner_adds_manager_and_operator(self, make_user, make_merchant):
        owner, manager, operator = make_user(), make_user(), make_user()
        merchant = make_merchant(owner=owner)
        services.add_member(
            merchant=merchant, actor=owner, email=manager.email, role="MERCHANT_MANAGER"
        )
        services.add_member(
            merchant=merchant, actor=owner, email=operator.email, role="MERCHANT_OPERATOR"
        )
        manager.refresh_from_db()
        assert manager.role == Role.MERCHANT_MANAGER
        assert services.can_manage(manager, merchant)
        assert services.can_publish(operator, merchant)
        assert not services.can_manage(operator, merchant)

    def test_only_owner_manages_team(self, make_user, make_merchant):
        owner, manager, other = make_user(), make_user(), make_user()
        merchant = make_merchant(owner=owner)
        services.add_member(
            merchant=merchant, actor=owner, email=manager.email, role="MERCHANT_MANAGER"
        )
        with pytest.raises(PermissionDenied):
            services.add_member(
                merchant=merchant, actor=manager, email=other.email, role="MERCHANT_OPERATOR"
            )

    def test_cannot_add_owner_role_or_unknown_user(self, make_user, make_merchant):
        owner, other = make_user(), make_user()
        merchant = make_merchant(owner=owner)
        with pytest.raises(ValidationError):
            services.add_member(
                merchant=merchant, actor=owner, email=other.email, role="MERCHANT_OWNER"
            )
        with pytest.raises(ValidationError):
            services.add_member(
                merchant=merchant, actor=owner, email="nobody@example.com", role="MERCHANT_MANAGER"
            )

    def test_owner_cannot_be_removed_or_demoted(self, make_user, make_merchant):
        owner = make_user()
        merchant = make_merchant(owner=owner)
        with pytest.raises(ValidationError):
            services.remove_member(merchant=merchant, actor=owner, user_id=owner.pk)
        with pytest.raises(ValidationError):
            services.add_member(
                merchant=merchant, actor=owner, email=owner.email, role="MERCHANT_MANAGER"
            )

    def test_removed_member_loses_access(self, make_user, make_merchant):
        owner, operator = make_user(), make_user()
        merchant = make_merchant(owner=owner)
        services.add_member(
            merchant=merchant, actor=owner, email=operator.email, role="MERCHANT_OPERATOR"
        )
        services.remove_member(merchant=merchant, actor=owner, user_id=operator.pk)
        assert not services.can_publish(operator, merchant)


@pytest.mark.django_db
class TestMerchantApi:
    def test_full_flow_over_http(self, make_user, login_as, api):
        owner = make_user()
        client = login_as(owner)
        created = client.post(
            "/api/v1/merchants/",
            {"legal_name": "Mercantil LTDA", "trade_name": "Mercantil", "cnpj": VALID_CNPJ},
            format="json",
        )
        assert created.status_code == 201
        mid = created.json()["id"]
        submitted = client.post(
            f"/api/v1/merchants/{mid}/verification/", {"to": "UNDER_REVIEW"}, format="json"
        )
        assert submitted.status_code == 200

        api.credentials()
        client = login_as(make_user(role=Role.MODERATOR))
        queue = client.get("/api/v1/merchants/review-queue/").json()
        assert [m["id"] for m in queue] == [mid]
        done = client.post(
            f"/api/v1/merchants/{mid}/verification/", {"to": "VERIFIED"}, format="json"
        )
        assert done.status_code == 200
        assert done.json()["is_verified"] is True

    def test_strangers_cannot_see_or_move_a_merchant(self, make_user, login_as, make_merchant):
        merchant = make_merchant()
        client = login_as(make_user())
        assert client.get(f"/api/v1/merchants/{merchant.pk}/").status_code == 403
        moved = client.post(
            f"/api/v1/merchants/{merchant.pk}/verification/", {"to": "UNDER_REVIEW"}, format="json"
        )
        assert moved.status_code == 403

    def test_review_queue_requires_permission(self, make_user, login_as):
        assert login_as(make_user()).get("/api/v1/merchants/review-queue/").status_code == 403

    def test_invalid_transition_is_400(self, make_user, login_as, make_merchant):
        owner = make_user()
        merchant = make_merchant(owner=owner)
        client = login_as(owner)
        response = client.post(
            f"/api/v1/merchants/{merchant.pk}/verification/", {"to": "VERIFIED"}, format="json"
        )
        assert response.status_code == 400
