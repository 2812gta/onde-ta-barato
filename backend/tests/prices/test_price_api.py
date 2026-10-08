import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.prices.models import PriceObservation
from tests.conftest import FORTALEZA, MARACANAU, NEAR

SEARCH = {"lat": MARACANAU[0], "lon": MARACANAU[1], "radius_km": 5}


@pytest.fixture
def world(make_user, make_merchant, make_store, make_variant):
    """A verified merchant's store, an unverified merchant's store and a far-away store."""
    verified_owner, plain_owner = make_user(), make_user()
    verified = make_merchant(owner=verified_owner, verified=True, trade_name="Mercantil Verificado")
    plain = make_merchant(owner=plain_owner, trade_name="Mercantil Novo")
    return {
        "variant": make_variant(),  # Arroz Tio João 5 kg, category mercearia (ttl 240h)
        "near": make_store(merchant=verified, coords=NEAR, name="Perto"),
        "center": make_store(merchant=plain, coords=MARACANAU, name="Centro"),
        "far": make_store(merchant=plain, coords=FORTALEZA, name="Longe"),
        "verified_owner": verified_owner,
        "plain_owner": plain_owner,
    }


def seed(world, store, price, source="MERCHANT", hours_ago=1, condition="NORMAL", user=None, **kw):
    return PriceObservation.objects.create(
        product_variant=world["variant"],
        store=world[store],
        price=Decimal(price),
        source=source,
        payment_condition=condition,
        collected_at=timezone.now() - timedelta(hours=hours_ago),
        confidence_score=Decimal("0.6"),
        confidence_level="MEDIUM",
        created_by=user,
        **kw,
    )


def search(client, world):
    response = client.post(
        f"/api/v1/variants/{world['variant'].pk}/prices/search/", SEARCH, format="json"
    )
    assert response.status_code == 200, response.content
    return response.json()


@pytest.mark.django_db
class TestPublishingOverHttp:
    def test_merchant_publishes_and_repeating_is_deduplicated(self, world, login_as):
        client = login_as(world["plain_owner"])
        body = {"variant_id": str(world["variant"].pk), "price": "24.90"}
        first = client.post(f"/api/v1/stores/{world['center'].pk}/prices/", body, format="json")
        again = client.post(f"/api/v1/stores/{world['center'].pk}/prices/", body, format="json")
        assert (first.status_code, again.status_code) == (201, 200)
        assert first.json()["deduplicated"] is False and again.json()["deduplicated"] is True
        price = first.json()["price"]
        assert price["source"] == "MERCHANT"
        assert price["status"] == "CURRENT"
        assert price["unit_price"]["display"] == "R$ 4,98/kg"
        assert price["disclaimer"] == "Pode haver diferença no caixa."
        assert PriceObservation.objects.count() == 1

    def test_stranger_cannot_publish_as_a_merchant(self, world, login_as, make_user):
        client = login_as(make_user())
        response = client.post(
            f"/api/v1/stores/{world['center'].pk}/prices/",
            {"variant_id": str(world["variant"].pk), "price": "1.00"},
            format="json",
        )
        assert response.status_code == 403

    def test_rival_merchant_cannot_publish_to_my_store(self, world, login_as):
        client = login_as(world["plain_owner"])
        response = client.post(
            f"/api/v1/stores/{world['near'].pk}/prices/",
            {"variant_id": str(world["variant"].pk), "price": "1.00"},
            format="json",
        )
        assert response.status_code == 403

    @pytest.mark.parametrize("price", ["0", "-5", "abc", "100000.00", "1.999"])
    def test_invalid_prices_are_400(self, world, login_as, price):
        client = login_as(world["plain_owner"])
        response = client.post(
            f"/api/v1/stores/{world['center'].pk}/prices/",
            {"variant_id": str(world["variant"].pk), "price": price},
            format="json",
        )
        assert response.status_code == 400

    def test_consumer_reports_with_location_and_coordinates_are_not_echoed(
        self, world, login_as, make_user
    ):
        client = login_as(make_user())
        response = client.post(
            f"/api/v1/stores/{world['center'].pk}/prices/report/",
            {
                "variant_id": str(world["variant"].pk),
                "price": "23.90",
                "lat": NEAR[0],
                "lon": NEAR[1],
            },
            format="json",
        )
        assert response.status_code == 201
        data = response.json()["price"]
        assert data["source"] == "USER" and data["location_verified"] is True
        assert str(NEAR[0]) not in json.dumps(data)

    def test_store_staff_report_is_refused(self, world, login_as):
        client = login_as(world["plain_owner"])
        response = client.post(
            f"/api/v1/stores/{world['center'].pk}/prices/report/",
            {"variant_id": str(world["variant"].pk), "price": "20.00"},
            format="json",
        )
        assert response.status_code == 400

    def test_anonymous_cannot_write_or_read(self, world, api):
        assert (
            api.post(f"/api/v1/stores/{world['center'].pk}/prices/", {}, format="json").status_code
            == 401
        )
        assert (
            api.post(
                f"/api/v1/variants/{world['variant'].pk}/prices/search/", SEARCH, format="json"
            ).status_code
            == 401
        )


@pytest.mark.django_db
class TestSearchTransparency:
    def test_lists_nearby_stores_with_prices_ordered_by_distance_only(
        self, world, login_as, make_user
    ):
        seed(world, "near", "26.00")
        seed(world, "center", "22.00")  # cheaper but farther: must NOT be reordered by price
        seed(world, "far", "10.00")  # outside the 5 km radius
        data = search(login_as(make_user()), world)
        assert [r["store"]["name"] for r in data["results"]] == ["Centro", "Perto"]
        distances = [r["store"]["distance_m"] for r in data["results"]]
        assert distances == sorted(distances)
        assert (data["stores_in_radius"], data["stores_with_price"]) == (2, 2)
        assert "Longe" not in str(data)

    def test_response_makes_no_best_price_claim(self, world, login_as, make_user):
        seed(world, "near", "26.00")
        seed(world, "center", "22.00")
        body = json.dumps(search(login_as(make_user()), world)).lower()
        for word in (
            "cheapest",
            "best",
            "melhor",
            "mais barato",
            "menor preço",
            "rank",
            "recommended",
        ):
            assert word not in body, word

    def test_every_price_shows_source_age_status_confidence_and_unit_price(
        self, world, login_as, make_user
    ):
        seed(world, "near", "24.90", hours_ago=3)
        price = search(login_as(make_user()), world)["results"][0]["prices"][0]
        for key in (
            "source",
            "collected_at",
            "age_hours",
            "status",
            "verification",
            "confidence_score",
            "confidence_level",
            "confidence_factors",
            "unit_price",
            "payment_condition",
            "disclaimer",
        ):
            assert key in price, key
        assert price["age_hours"] == pytest.approx(3, abs=0.1)
        assert price["unit_price"] == {"amount": "4.9800", "per": "kg", "display": "R$ 4,98/kg"}

    def test_conflicting_sources_are_both_shown_and_flagged(self, world, login_as, make_user):
        seed(world, "center", "20.00", source="MERCHANT")
        seed(world, "center", "18.90", source="USER", hours_ago=0.5, user=make_user())
        result = search(login_as(make_user()), world)["results"][0]
        assert result["conflict"] is True
        assert sorted(p["price"] for p in result["prices"]) == ["18.90", "20.00"]
        assert {p["status"] for p in result["prices"]} == {"CONFLICTING"}
        assert {p["source"] for p in result["prices"]} == {"MERCHANT", "USER"}

    def test_close_prices_are_not_a_conflict(self, world, login_as, make_user):
        seed(world, "center", "20.00", source="MERCHANT")
        seed(world, "center", "20.10", source="USER", user=make_user())  # 0.5% apart
        result = search(login_as(make_user()), world)["results"][0]
        assert result["conflict"] is False

    def test_different_payment_conditions_are_not_conflicts(self, world, login_as, make_user):
        seed(world, "center", "21.90", condition="NORMAL")
        seed(world, "center", "19.90", condition="PIX")
        result = search(login_as(make_user()), world)["results"][0]
        assert result["conflict"] is False
        assert {p["payment_condition"] for p in result["prices"]} == {"NORMAL", "PIX"}

    def test_old_prices_are_labelled_not_hidden(self, world, login_as, make_user):
        # mercearia ttl = 240h: 300h is STALE, 600h is EXPIRED
        seed(world, "near", "24.00", hours_ago=300)
        seed(world, "center", "24.00", hours_ago=600)
        results = {
            r["store"]["name"]: r["prices"][0]
            for r in search(login_as(make_user()), world)["results"]
        }
        assert results["Perto"]["status"] == "STALE"
        assert results["Centro"]["status"] == "EXPIRED"
        assert results["Centro"]["confidence_level"] == "LOW"

    def test_expired_promotion_is_expired_even_if_recent(self, world, login_as, make_user):
        seed(
            world,
            "near",
            "19.90",
            hours_ago=2,
            valid_until=timezone.now() - timedelta(hours=1),
            is_promotional=True,
        )
        assert (
            search(login_as(make_user()), world)["results"][0]["prices"][0]["status"] == "EXPIRED"
        )

    def test_very_old_observations_leave_listings_but_stay_in_history(
        self, world, login_as, make_user
    ):
        seed(world, "near", "24.00", hours_ago=24 * 100)
        client = login_as(make_user())
        assert search(client, world)["results"] == []
        history = client.get(
            f"/api/v1/variants/{world['variant'].pk}/price-history/",
            {"store": str(world["near"].pk)},
        )
        assert len(history.json()) == 1

    def test_only_the_latest_observation_per_source_is_listed(self, world, login_as, make_user):
        seed(world, "near", "25.00", hours_ago=50)
        seed(world, "near", "27.00", hours_ago=2)
        prices = search(login_as(make_user()), world)["results"][0]["prices"]
        assert [p["price"] for p in prices] == ["27.00"]

    def test_location_must_be_valid(self, world, login_as, make_user):
        client = login_as(make_user())
        response = client.post(
            f"/api/v1/variants/{world['variant'].pk}/prices/search/",
            {"lat": 100, "lon": 0},
            format="json",
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestVerificationStatus:
    def test_verified_merchant_price_is_verified_others_are_not(self, world, login_as, make_user):
        seed(world, "near", "24.00")  # store of the VERIFIED merchant
        seed(world, "center", "24.00")  # store of the unverified merchant
        by_store = {
            r["store"]["name"]: r["prices"][0]
            for r in search(login_as(make_user()), world)["results"]
        }
        assert by_store["Perto"]["verification"] == "VERIFIED"
        assert by_store["Centro"]["verification"] == "UNVERIFIED"
        assert by_store["Perto"]["confidence_score"] > by_store["Centro"]["confidence_score"]

    def test_user_price_becomes_verified_only_after_independent_confirmations(
        self, world, login_as, make_user, api
    ):
        author = make_user()
        obs = seed(world, "center", "23.00", source="USER", user=author)
        for index in range(2):
            api.credentials()
            client = login_as(make_user())
            assert (
                client.post(
                    f"/api/v1/prices/{obs.pk}/confirmations/", {"agrees": True}, format="json"
                ).status_code
                == 201
            )
            api.credentials()
            price = search(login_as(make_user()), world)["results"][0]["prices"][0]
            assert price["confirmations"] == index + 1
            assert price["verification"] == ("VERIFIED" if index == 1 else "UNVERIFIED")

    def test_a_dispute_blocks_verification(self, world, login_as, make_user, api):
        obs = seed(world, "center", "23.00", source="USER", user=make_user())
        for agrees in (True, True, False):
            api.credentials()
            login_as(make_user()).post(
                f"/api/v1/prices/{obs.pk}/confirmations/", {"agrees": agrees}, format="json"
            )
        api.credentials()
        price = search(login_as(make_user()), world)["results"][0]["prices"][0]
        assert (price["confirmations"], price["contradictions"]) == (2, 1)
        assert price["verification"] == "UNVERIFIED"

    def test_confirming_twice_or_own_price_is_a_400(self, world, login_as, make_user):
        author = make_user()
        obs = seed(world, "center", "23.00", source="USER", user=author)
        assert (
            login_as(author)
            .post(f"/api/v1/prices/{obs.pk}/confirmations/", {"agrees": True}, format="json")
            .status_code
            == 400
        )
        other = make_user()
        client = login_as(other)
        assert (
            client.post(
                f"/api/v1/prices/{obs.pk}/confirmations/", {"agrees": True}, format="json"
            ).status_code
            == 201
        )
        assert (
            client.post(
                f"/api/v1/prices/{obs.pk}/confirmations/", {"agrees": True}, format="json"
            ).status_code
            == 400
        )


@pytest.mark.django_db
class TestHistoryEndpoint:
    def test_answers_what_was_the_previous_price_without_exposing_people(self, world, login_as):
        client = login_as(world["plain_owner"])
        variant = str(world["variant"].pk)
        base = {"variant_id": variant}
        for price in ("25.90", "27.90", "24.90", "23.90"):
            client.post(
                f"/api/v1/stores/{world['center'].pk}/prices/",
                {**base, "price": price},
                format="json",
            )
        history = client.get(
            f"/api/v1/variants/{variant}/price-history/", {"store": str(world["center"].pk)}
        ).json()
        assert [h["price"] for h in history] == ["23.90", "24.90", "27.90", "25.90"]
        assert [h["previous_price"] for h in history] == ["24.90", "27.90", "25.90", None]
        assert {h["contributor"] for h in history} == {"ESTABELECIMENTO"}
        payload = json.dumps(history)
        assert str(world["plain_owner"].pk) not in payload
        assert "created_by" not in payload and "email" not in payload

    def test_store_parameter_is_required(self, world, login_as, make_user):
        response = login_as(make_user()).get(
            f"/api/v1/variants/{world['variant'].pk}/price-history/"
        )
        assert response.status_code == 400

    def test_filter_by_payment_condition(self, world, login_as, make_user):
        seed(world, "center", "21.00", condition="NORMAL")
        seed(world, "center", "19.00", condition="PIX")
        client = login_as(make_user())
        data = client.get(
            f"/api/v1/variants/{world['variant'].pk}/price-history/",
            {"store": str(world["center"].pk), "payment_condition": "PIX"},
        ).json()
        assert [h["price"] for h in data] == ["19.00"]
