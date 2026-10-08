from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.core import clock
from apps.promotions import selectors, services
from apps.promotions.models import Promotion

THREE_FOR_20 = {"type": "FIXED_PRICE", "bundle_quantity": 3, "bundle_price": "20.00"}


@pytest.fixture
def shop(make_user, make_merchant, make_store, make_variant):
    owner = make_user()
    merchant = make_merchant(owner=owner)
    return {
        "owner": owner,
        "merchant": merchant,
        "store": make_store(merchant=merchant),
        "variant": make_variant(),
        "stranger": make_user(),
    }


def create(shop, rule=None, actor=None, **kw):
    return services.create_promotion(
        store=shop["store"],
        actor=actor or shop["owner"],
        variant=shop["variant"],
        title=kw.pop("title", "3 por R$ 20"),
        rule=rule or THREE_FOR_20,
        **kw,
    )


@pytest.mark.django_db
class TestServices:
    def test_member_creates_promotion_and_it_is_audited(self, shop):
        promotion = create(shop)
        assert promotion.rule == THREE_FOR_20 and promotion.is_active
        assert AuditLog.objects.filter(
            action="promotion.created", entity_id=str(promotion.pk)
        ).exists()

    def test_stranger_and_rival_cannot_create(self, shop, make_merchant):
        with pytest.raises(PermissionDenied):
            create(shop, actor=shop["stranger"])
        rival = make_merchant(trade_name="Rival").memberships.get().user
        with pytest.raises(PermissionDenied):
            create(shop, actor=rival)

    def test_invalid_rule_is_refused_before_saving(self, shop):
        with pytest.raises(ValidationError):
            create(shop, rule={"type": "BUY_X_PAY_Y", "buy": 3, "pay": 3})
        assert Promotion.objects.count() == 0

    def test_validity_must_follow_start(self, shop):
        now = timezone.now()
        with pytest.raises(ValidationError):
            create(shop, valid_from=now, valid_until=now - timedelta(days=1))

    def test_deactivation_keeps_the_record(self, shop):
        promotion = create(shop)
        services.deactivate_promotion(promotion=promotion, actor=shop["owner"])
        promotion.refresh_from_db()
        assert promotion.is_active is False
        assert Promotion.objects.count() == 1
        entry = AuditLog.objects.get(action="promotion.deactivated")
        assert entry.previous_value == {"is_active": True}

    def test_only_publishers_can_deactivate(self, shop):
        promotion = create(shop)
        with pytest.raises(PermissionDenied):
            services.deactivate_promotion(promotion=promotion, actor=shop["stranger"])

    def test_database_rejects_inverted_validity(self, shop):
        from django.db import IntegrityError, transaction

        now = timezone.now()
        with pytest.raises(IntegrityError), transaction.atomic():
            Promotion.objects.create(
                store=shop["store"],
                product_variant=shop["variant"],
                title="x",
                rule=THREE_FOR_20,
                valid_from=now,
                valid_until=now - timedelta(hours=1),
            )


@pytest.mark.django_db
class TestSelectors:
    def test_status_lifecycle(self, shop):
        base = timezone.now()
        future = create(shop, valid_from=base + timedelta(days=1))
        past = create(
            shop, valid_from=base - timedelta(days=2), valid_until=base - timedelta(days=1)
        )
        live = create(shop)
        off = create(shop)
        services.deactivate_promotion(promotion=off, actor=shop["owner"])
        now = clock.now()  # same clock that stamped the rows
        states = {p.pk: selectors.status_of(p, now) for p in (future, past, live, off)}
        assert states == {
            future.pk: "SCHEDULED",
            past.pk: "EXPIRED",
            live.pk: "ACTIVE",
            off.pk: "INACTIVE",
        }

    def test_running_promotions_only_returns_live_ones_grouped(self, shop):
        create(shop, valid_from=timezone.now() + timedelta(days=1))
        live = create(shop)
        now = clock.now()
        grouped = selectors.running_promotions(
            store_ids=[shop["store"].pk], variant_ids=[shop["variant"].pk], now=now
        )
        assert [p.pk for p in grouped[(shop["store"].pk, shop["variant"].pk)]] == [live.pk]

    def test_confirmed_only_for_verified_merchants(self, shop, make_merchant, make_store):
        assert selectors.is_confirmed(create(shop)) is False
        verified = make_merchant(verified=True, trade_name="Verificado")
        store = make_store(merchant=verified, name="Loja V")
        promotion = services.create_promotion(
            store=store,
            actor=verified.memberships.get().user,
            variant=shop["variant"],
            title="10%",
            rule={"type": "PERCENTAGE", "percent": "10"},
        )
        assert selectors.is_confirmed(promotion) is True


@pytest.mark.django_db
class TestApi:
    def test_create_list_and_deactivate_over_http(self, shop, login_as):
        client = login_as(shop["owner"])
        body = {"variant_id": str(shop["variant"].pk), "title": "3 por R$ 20", "rule": THREE_FOR_20}
        created = client.post(f"/api/v1/stores/{shop['store'].pk}/promotions/", body, format="json")
        assert created.status_code == 201
        data = created.json()
        assert (data["status"], data["confirmed"]) == ("ACTIVE", False)  # merchant not verified yet
        listing = client.get(f"/api/v1/stores/{shop['store'].pk}/promotions/").json()
        assert [p["id"] for p in listing] == [data["id"]]
        assert client.delete(f"/api/v1/promotions/{data['id']}/").status_code == 204
        assert client.get(f"/api/v1/stores/{shop['store'].pk}/promotions/").json() == []

    def test_invalid_rule_is_a_400_with_the_reason(self, shop, login_as):
        client = login_as(shop["owner"])
        body = {
            "variant_id": str(shop["variant"].pk),
            "title": "x",
            "rule": {"type": "PERCENTAGE", "percent": "250"},
        }
        response = client.post(
            f"/api/v1/stores/{shop['store'].pk}/promotions/", body, format="json"
        )
        assert response.status_code == 400
        assert "percent" in str(response.json())

    def test_float_in_rule_is_refused_over_http_too(self, shop, login_as):
        client = login_as(shop["owner"])
        body = {
            "variant_id": str(shop["variant"].pk),
            "title": "x",
            "rule": {"type": "PERCENTAGE", "percent": 10.5},
        }
        assert (
            client.post(
                f"/api/v1/stores/{shop['store'].pk}/promotions/", body, format="json"
            ).status_code
            == 400
        )

    def test_stranger_cannot_publish(self, shop, login_as):
        client = login_as(shop["stranger"])
        body = {"variant_id": str(shop["variant"].pk), "title": "x", "rule": THREE_FOR_20}
        assert (
            client.post(
                f"/api/v1/stores/{shop['store'].pk}/promotions/", body, format="json"
            ).status_code
            == 403
        )

    def test_calculator_matches_the_spec_example(self, shop, login_as):
        client = login_as(shop["stranger"])
        response = client.post(
            "/api/v1/promotions/calculate/",
            {"unit_price": "10.00", "quantity": "5", "rule": THREE_FOR_20},
            format="json",
        )
        assert response.status_code == 200
        data = response.json()
        assert (data["gross"], data["net"], data["savings"]) == ("50.00", "40.00", "10.00")
        assert data["applicable"] is True and data["steps"]

    def test_calculator_explains_why_not_applicable(self, shop, login_as):
        client = login_as(shop["stranger"])
        response = client.post(
            "/api/v1/promotions/calculate/",
            {
                "unit_price": "100.00",
                "quantity": "1",
                "rule": {"type": "PIX_PRICE", "percent": "5"},
            },
            format="json",
        )
        data = response.json()
        assert data["applicable"] is False and "Pix" in data["reason"]
        assert data["net"] == data["gross"] == "100.00"

    def test_calculator_applies_pix_when_selected(self, shop, login_as):
        client = login_as(shop["stranger"])
        response = client.post(
            "/api/v1/promotions/calculate/",
            {
                "unit_price": "100.00",
                "quantity": "1",
                "payment_condition": "PIX",
                "rule": {"type": "PIX_PRICE", "percent": "5"},
            },
            format="json",
        )
        assert response.json()["net"] == "95.00"

    def test_requires_authentication(self, api, db):
        assert api.post("/api/v1/promotions/calculate/", {}, format="json").status_code == 401


@pytest.mark.django_db
def test_a_promotion_is_active_the_moment_it_is_created(shop):
    """Regression: rows are stamped by the monotonic clock, so 'now' must come from it too.

    With the OS clock as 'now', a promotion created microseconds earlier could look SCHEDULED
    (intermittent on Windows, where the OS clock ticks every 15.6 ms).
    """
    for _ in range(150):
        promotion = create(shop)
        assert selectors.status_of(promotion, clock.now()) == "ACTIVE"
        running = selectors.running_promotions(
            store_ids=[shop["store"].pk], variant_ids=[shop["variant"].pk], now=clock.now()
        )
        assert promotion.pk in [p.pk for p in running[(shop["store"].pk, shop["variant"].pk)]]
        promotion.hard_delete()


@pytest.mark.django_db
def test_api_reports_a_just_created_promotion_as_active(shop, login_as):
    """Same regression through the HTTP layer (the serializer computes the status)."""
    client = login_as(shop["owner"])
    body = {"variant_id": str(shop["variant"].pk), "title": "3 por R$ 20", "rule": THREE_FOR_20}
    for _ in range(80):
        created = client.post(f"/api/v1/stores/{shop['store'].pk}/promotions/", body, format="json")
        assert created.json()["status"] == "ACTIVE"
