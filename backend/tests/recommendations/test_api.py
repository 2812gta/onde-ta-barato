"""End-to-end recommendation tests against PostGIS.

User stands in Maracanaú center. Stores: S2 right there (0 m), S1 ~0.4 km away, S3 in
Fortaleza (~18.4 km). Prices are merchant prices unless stated.
"""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.merchants.models import Merchant, VerificationStatus
from apps.prices.models import PriceObservation
from apps.promotions import services as promotion_services
from tests.conftest import FORTALEZA, MARACANAU, NEAR

BASKET_URL = "/api/v1/recommendations/basket/"
LOCATION = {"lat": MARACANAU[0], "lon": MARACANAU[1], "radius_km": 25}


@pytest.fixture
def town(make_user, make_merchant, make_store, make_variant):
    rice = make_variant()  # Arroz Tio João 5 kg
    beans = make_variant(name="Feijão Carioca", brand="Camil", quantity="1", unit="kg")
    owners = {k: make_user() for k in ("s1", "s2", "s3")}
    merchants = {
        "s1": make_merchant(owner=owners["s1"], verified=True, trade_name="Verificado"),
        "s2": make_merchant(owner=owners["s2"], trade_name="Centro"),
        "s3": make_merchant(owner=owners["s3"], trade_name="Capital"),
    }
    return {
        "rice": rice,
        "beans": beans,
        "owners": owners,
        "merchants": merchants,
        "s1": make_store(merchant=merchants["s1"], coords=NEAR, name="S1 Perto"),
        "s2": make_store(merchant=merchants["s2"], coords=MARACANAU, name="S2 Centro"),
        "s3": make_store(merchant=merchants["s3"], coords=FORTALEZA, name="S3 Capital"),
    }


def price(
    town,
    store,
    variant,
    value,
    *,
    hours_ago=1,
    source="MERCHANT",
    condition="NORMAL",
    user=None,
    **kw,
):
    return PriceObservation.objects.create(
        product_variant=town[variant],
        store=town[store],
        price=Decimal(value),
        source=source,
        payment_condition=condition,
        collected_at=timezone.now() - timedelta(hours=hours_ago),
        confidence_score=Decimal("0.6"),
        confidence_level="MEDIUM",
        created_by=user,
        **kw,
    )


def fill(town):
    """S1: 26+7  S2: 24+6.50  S3: 20+5 (rice, beans)."""
    for store, rice, beans in (
        ("s1", "26.00", "7.00"),
        ("s2", "24.00", "6.50"),
        ("s3", "20.00", "5.00"),
    ):
        price(town, store, "rice", rice)
        price(town, store, "beans", beans)


def ask(client, town, **overrides):
    body = {
        **LOCATION,
        "items": [
            {"variant_id": str(town["rice"].pk), "quantity": "1"},
            {"variant_id": str(town["beans"].pk), "quantity": "2"},
        ],
        **overrides,
    }
    response = client.post(BASKET_URL, body, format="json")
    assert response.status_code == 200, response.content
    return response.json()


@pytest.mark.django_db
class TestBasket:
    def test_picks_the_store_with_the_lowest_total_including_travel(
        self, town, login_as, make_user
    ):
        fill(town)
        data = ask(login_as(make_user()), town, mode="ECONOMIZAR_MAIS", max_stores=1)
        # S2: 24 + 2x6.50 = 37.00, 0 km. S1: 40.00 + ~0.4 km trip. S3: 30.00 + ~48 km of travel.
        assert data["verdict"] == "RECOMMENDED"
        best = data["best"]
        assert [s["name"] for s in best["stores"]] == ["S2 Centro"]
        assert best["items_total"] == "37.00"
        assert best["transport_cost"] == "0.00"
        assert best["effective_total"] == "37.00"
        s3 = next(a for a in data["alternatives"] if a["stores"][0]["name"] == "S3 Capital")
        assert s3["items_total"] == "30.00"
        assert Decimal(s3["transport_cost"]) > Decimal("30.00")  # travel eats the saving

    def test_without_travel_cost_the_cheapest_basket_wins(self, town, login_as, make_user):
        fill(town)
        data = ask(
            login_as(make_user()), town, mode="ECONOMIZAR_MAIS", max_stores=1, cost_per_km="0"
        )
        assert data["best"]["stores"][0]["name"] == "S3 Capital"
        assert data["best"]["effective_total"] == "30.00"

    def test_transport_uses_postgis_distance(self, town, login_as, make_user):
        fill(town)
        data = ask(login_as(make_user()), town, max_stores=1)
        s1 = next(
            p for p in [data["best"], *data["alternatives"]] if p["stores"][0]["name"] == "S1 Perto"
        )
        assert 300 < s1["stores"][0]["distance_m"] < 700
        # round trip x1.3 detour: ~0.5 km one way -> ~1.3 km at R$ 0.80/km, about R$ 1
        assert 0.5 < float(s1["transport_cost"]) < 2.0
        assert 1.0 < s1["route_km"] < 2.0

    def test_response_explains_itself_with_real_numbers(self, town, login_as, make_user):
        fill(town)
        data = ask(login_as(make_user()), town, max_stores=1)
        codes = {r["code"] for r in data["reasons"]}
        assert {"COVERAGE", "PRICE_VS_AVERAGE", "DISTANCE", "FRESHNESS"} <= codes
        coverage = next(r for r in data["reasons"] if r["code"] == "COVERAGE")
        assert coverage["text"] == "100% da sua lista disponível"
        assert "Os preços podem divergir do caixa." in data["warnings"]
        assumptions = data["assumptions"]
        assert (
            assumptions["cost_per_km"] == "0.80" and "linha reta" in assumptions["distance_basis"]
        )
        assert data["searched"] == {"stores_in_radius": 3, "stores_with_prices": 3}

    def test_split_between_two_stores_when_it_pays_off(self, town, login_as, make_user):
        # S1 has cheap rice, S2 has cheap beans; they are ~0.4 km apart.
        price(town, "s1", "rice", "20.00")
        price(town, "s1", "beans", "9.00")
        price(town, "s2", "rice", "28.00")
        price(town, "s2", "beans", "4.00")
        data = ask(login_as(make_user()), town, mode="ECONOMIZAR_MAIS", radius_km=5)
        best = data["best"]
        assert {s["name"] for s in best["stores"]} == {"S1 Perto", "S2 Centro"}
        assert {ln["label"].split()[0]: ln["store"] for ln in best["lines"]} == {
            "Arroz": "S1 Perto",
            "Feijão": "S2 Centro",
        }
        assert best["items_total"] == "28.00"
        assert any("2 paradas" in r["text"] for r in data["reasons"])

    def test_least_travel_mode_never_splits(self, town, login_as, make_user):
        price(town, "s1", "rice", "20.00")
        price(town, "s1", "beans", "9.00")
        price(town, "s2", "rice", "28.00")
        price(town, "s2", "beans", "4.00")
        data = ask(login_as(make_user()), town, mode="MENOS_DESLOCAMENTO", radius_km=5)
        assert all(len(p["stores"]) == 1 for p in [data["best"], *data["alternatives"]] if p)


@pytest.mark.django_db
class TestHonesty:
    def test_one_store_is_not_a_comparison(self, town, login_as, make_user):
        price(town, "s2", "rice", "24.00")
        price(town, "s2", "beans", "6.50")
        data = ask(login_as(make_user()), town)
        assert data["verdict"] == "INSUFFICIENT_DATA"
        assert data["message"] == "Não foi possível determinar o melhor mercado com segurança."
        assert data["best"] is None and data["reasons"] == []
        assert data["alternatives"]  # what we do know is still visible

    def test_no_prices_at_all(self, town, login_as, make_user):
        data = ask(login_as(make_user()), town)
        assert data["verdict"] == "INSUFFICIENT_DATA" and data["best"] is None

    def test_expired_prices_are_ignored_stale_ones_are_flagged(self, town, login_as, make_user):
        # rice ttl = 240 h: 300 h old is STALE, 700 h old is EXPIRED
        for store, hours in (("s1", 300), ("s2", 1), ("s3", 700)):
            price(town, store, "rice", "25.00", hours_ago=hours)
            price(town, store, "beans", "6.00", hours_ago=hours)
        data = ask(login_as(make_user()), town, radius_km=5, max_stores=1)
        assert data["searched"]["stores_with_prices"] == 2  # S3's expired prices never counted
        s1 = next(
            p for p in [data["best"], *data["alternatives"]] if p["stores"][0]["name"] == "S1 Perto"
        )
        assert {ln["price_freshness"] for ln in s1["lines"]} == {"STALE"}

    def test_conflicting_sources_use_the_higher_price_and_say_so(self, town, login_as, make_user):
        price(town, "s2", "rice", "20.00")
        price(town, "s2", "beans", "6.00")
        price(town, "s2", "rice", "18.00", source="USER", hours_ago=0.5, user=make_user())
        price(town, "s1", "rice", "40.00")
        price(town, "s1", "beans", "12.00")  # clearly worse
        data = ask(login_as(make_user()), town, radius_km=5, max_stores=1, cost_per_km="0")
        assert data["best"]["stores"][0]["name"] == "S2 Centro"  # so its conflict must be disclosed
        s2 = data["best"]
        rice = next(ln for ln in s2["lines"] if ln["label"].startswith("Arroz"))
        assert rice["price_conflict"] is True and rice["unit_price"] == "20.00"
        assert s2["items_total"] == "32.00"  # 20.00 + 2 x 6.00, not the 18.00
        assert s2["optimistic_total"] == "30.00"  # if the 18.00 report is the real one
        assert s2["conflicting_prices"] == 1
        warning = next(w for w in data["warnings"] if "conflitantes" in w)
        assert "R$ 32,00" in warning and "R$ 30,00" in warning

    def test_payment_method_decides_which_conditional_price_applies(
        self, town, login_as, make_user
    ):
        price(town, "s2", "rice", "24.00")
        price(town, "s2", "rice", "22.00", condition="PIX")
        price(town, "s2", "beans", "6.50")
        price(town, "s1", "rice", "25.00")
        price(town, "s1", "beans", "6.60")
        client = login_as(make_user())
        card = ask(
            client, town, radius_km=5, max_stores=1, cost_per_km="0", payment_condition="CREDIT"
        )
        pix = ask(client, town, radius_km=5, max_stores=1, cost_per_km="0", payment_condition="PIX")

        def rice_price(data):
            plans = [data["best"], *data["alternatives"]]
            s2 = next(p for p in plans if p and p["stores"][0]["name"] == "S2 Centro")
            return next(ln for ln in s2["lines"] if ln["label"].startswith("Arroz"))["unit_price"]

        assert rice_price(card) == "24.00"  # the Pix price is not offered to someone paying by card
        assert rice_price(pix) == "22.00"

    def test_partial_coverage_is_labelled_and_never_beats_a_complete_option(
        self, town, login_as, make_user
    ):
        price(town, "s2", "rice", "1.00")  # absurdly cheap but only half the list
        price(town, "s1", "rice", "26.00")
        price(town, "s1", "beans", "7.00")
        price(town, "s3", "rice", "27.00")
        price(town, "s3", "beans", "7.50")
        data = ask(login_as(make_user()), town, max_stores=1)
        assert data["best"]["complete"] is True
        partial = next(p for p in data["alternatives"] if not p["complete"])
        assert partial["missing_items"] and partial["coverage"] == 0.5


@pytest.mark.django_db
class TestPromotionsInRecommendations:
    RULE = {"type": "FIXED_PRICE", "bundle_quantity": 3, "bundle_price": "20.00"}

    def promote(self, town, store="s2"):
        owner = town["owners"][store]
        return promotion_services.create_promotion(
            store=town[store],
            actor=owner,
            variant=town["rice"],
            title="3 por R$ 20",
            rule=self.RULE,
        )

    def basket_of_five_rice(self, client, town, **kw):
        body = {
            **LOCATION,
            "radius_km": 5,
            "max_stores": 1,
            "cost_per_km": "0",
            "items": [{"variant_id": str(town["rice"].pk), "quantity": "5"}],
            **kw,
        }
        response = client.post(BASKET_URL, body, format="json")
        assert response.status_code == 200
        return response.json()

    def test_unverified_merchants_promotion_is_disclosed_but_not_counted(
        self, town, login_as, make_user
    ):
        price(town, "s2", "rice", "10.00")
        price(town, "s1", "rice", "10.50")
        self.promote(town)
        data = self.basket_of_five_rice(login_as(make_user()), town)
        plans = {p["stores"][0]["name"]: p for p in [data["best"], *data["alternatives"]] if p}
        assert plans["S2 Centro"]["items_total"] == "50.00"  # gross: promotion NOT applied
        assert plans["S2 Centro"]["unconfirmed_promotion_potential"] == "10.00"
        assert data["best"]["stores"][0]["name"] == "S2 Centro"
        assert plans["S2 Centro"]["promotions_applied"] == 0
        assert any("não confirmada" in w and "R$ 10,00" in w for w in data["warnings"])

    def test_verified_merchants_promotion_is_applied(self, town, login_as, make_user):
        price(town, "s2", "rice", "10.00")
        price(town, "s1", "rice", "10.50")
        self.promote(town)
        Merchant.objects.filter(pk=town["merchants"]["s2"].pk).update(
            status=VerificationStatus.VERIFIED
        )
        data = self.basket_of_five_rice(login_as(make_user()), town)
        s2 = next(
            p
            for p in [data["best"], *data["alternatives"]]
            if p["stores"][0]["name"] == "S2 Centro"
        )
        assert s2["items_total"] == "40.00"  # 3 for R$ 20 + 2 x R$ 10 (the spec example)
        assert s2["savings_total"] == "10.00" and s2["promotions_applied"] == 1
        assert s2["lines"][0]["promotion"] == "3 por R$ 20"

    def test_deactivated_promotion_stops_counting(self, town, login_as, make_user):
        price(town, "s2", "rice", "10.00")
        price(town, "s1", "rice", "10.50")
        promotion = self.promote(town)
        Merchant.objects.filter(pk=town["merchants"]["s2"].pk).update(
            status=VerificationStatus.VERIFIED
        )
        promotion_services.deactivate_promotion(promotion=promotion, actor=town["owners"]["s2"])
        data = self.basket_of_five_rice(login_as(make_user()), town)
        s2 = next(
            p
            for p in [data["best"], *data["alternatives"]]
            if p["stores"][0]["name"] == "S2 Centro"
        )
        assert s2["items_total"] == "50.00" and s2["promotions_applied"] == 0


@pytest.mark.django_db
class TestComparison:
    def compare(self, client, town, **extra):
        response = client.post(
            f"/api/v1/variants/{town['rice'].pk}/compare/", {**LOCATION, **extra}, format="json"
        )
        assert response.status_code == 200, response.content
        return response.json()

    def test_ranks_by_unit_price_and_labels_the_lowest_honestly(self, town, login_as, make_user):
        fill(town)
        data = self.compare(login_as(make_user()), town)
        assert [r["store"]["name"] for r in data["results"]] == [
            "S3 Capital",
            "S2 Centro",
            "S1 Perto",
        ]
        assert [r["rank"] for r in data["results"]] == [1, 2, 3]
        assert data["results"][0]["unit_price"]["display"] == "R$ 4,00/kg"  # 20.00 / 5 kg
        assert data["label"] == "Menor preço encontrado na nossa base"
        analysis = data["analysis"]
        assert (analysis["stores_in_radius"], analysis["stores_with_price"]) == (3, 3)
        assert analysis["coverage"] == 1.0 and analysis["generated_at"]
        assert "Pode haver diferença no caixa." in data["notes"]

    def test_never_claims_cheapest_with_a_single_price(self, town, login_as, make_user):
        price(town, "s2", "rice", "24.00")
        data = self.compare(login_as(make_user()), town)
        assert data["label"] is None
        assert any("não há com o que comparar" in n for n in data["notes"])

    def test_no_prices(self, town, login_as, make_user):
        data = self.compare(login_as(make_user()), town)
        assert data["results"] == [] and data["label"] is None

    def test_withholds_the_claim_when_the_lowest_price_is_disputed(self, town, login_as, make_user):
        price(town, "s3", "rice", "20.00")
        price(town, "s3", "rice", "17.00", source="USER", user=make_user())
        price(town, "s2", "rice", "24.00")
        data = self.compare(login_as(make_user()), town)
        top = data["results"][0]
        assert top["store"]["name"] == "S3 Capital" and top["price_conflict"] is True
        assert top["price"] == "20.00" and top["price_range"] == ["17.00", "20.00"]
        assert data["label"] is None
        assert any("conflitantes" in n for n in data["notes"])

    def test_ties_share_a_rank_and_are_reported(self, town, login_as, make_user):
        price(town, "s1", "rice", "24.00")
        price(town, "s2", "rice", "24.00")
        price(town, "s3", "rice", "30.00")
        data = self.compare(login_as(make_user()), town)
        assert [r["rank"] for r in data["results"]] == [1, 1, 3]
        assert [r["store"]["name"] for r in data["results"][:2]] == [
            "S2 Centro",
            "S1 Perto",
        ]  # nearer first
        assert any("empatadas" in n for n in data["notes"])

    def test_old_lowest_price_is_flagged(self, town, login_as, make_user):
        price(town, "s3", "rice", "20.00", hours_ago=300)
        price(town, "s2", "rice", "24.00")
        data = self.compare(login_as(make_user()), town)
        assert data["label"] == "Menor preço encontrado na nossa base"
        assert any("desatualizado" in n for n in data["notes"])

    def test_merchant_verification_does_not_change_the_order(self, town, login_as, make_user):
        """S1's merchant is verified, S2's is not, S3's is not: only the price decides."""
        price(town, "s1", "rice", "30.00")
        price(town, "s2", "rice", "22.00")
        price(town, "s3", "rice", "25.00")
        data = self.compare(login_as(make_user()), town)
        assert [r["store"]["name"] for r in data["results"]] == [
            "S2 Centro",
            "S3 Capital",
            "S1 Perto",
        ]
        verified = next(r for r in data["results"] if r["store"]["merchant_verified"])
        assert verified["store"]["name"] == "S1 Perto" and verified["rank"] == 3

    def test_confidence_is_shown_but_does_not_reorder(self, town, login_as, make_user):
        price(town, "s2", "rice", "22.00", hours_ago=400)  # old, so low confidence, still cheapest
        price(town, "s1", "rice", "23.00", hours_ago=1)
        data = self.compare(login_as(make_user()), town)
        first, second = data["results"]
        assert first["store"]["name"] == "S2 Centro" and first["confidence"] < second["confidence"]


@pytest.mark.django_db
class TestPrivacyAndValidation:
    def test_requires_authentication(self, api, town):
        assert api.post(BASKET_URL, {}, format="json").status_code == 401
        assert (
            api.post(
                f"/api/v1/variants/{town['rice'].pk}/compare/", LOCATION, format="json"
            ).status_code
            == 401
        )

    def test_location_never_goes_in_the_url(self, town, login_as, make_user):
        client = login_as(make_user())
        assert client.get(BASKET_URL + "?lat=-3.8&lon=-38.6").status_code == 405
        assert (
            client.get(f"/api/v1/variants/{town['rice'].pk}/compare/?lat=-3.8").status_code == 405
        )

    def test_user_location_is_not_stored_or_echoed(self, town, login_as, make_user):
        fill(town)
        data = ask(login_as(make_user()), town)
        payload = json.dumps(data, default=str)
        assert str(MARACANAU[0]) not in payload and str(MARACANAU[1]) not in payload
        dumped = " ".join(str(r) for r in AuditLog.objects.values_list("new_value", "metadata"))
        assert str(MARACANAU[0]) not in dumped

    @pytest.mark.parametrize(
        "patch",
        [
            {"items": []},
            {"mode": "CHEAPEST_EVER"},
            {"max_stores": 3},
            {"radius_km": 99},
            {"cost_per_km": "-1"},
            {"lat": 120},
            {"payment_condition": "BITCOIN"},
        ],
    )
    def test_invalid_requests_are_400(self, town, login_as, make_user, patch):
        client = login_as(make_user())
        body = {
            **LOCATION,
            "items": [{"variant_id": str(town["rice"].pk), "quantity": "1"}],
            **patch,
        }
        assert client.post(BASKET_URL, body, format="json").status_code == 400

    def test_repeated_product_is_refused(self, town, login_as, make_user):
        client = login_as(make_user())
        item = {"variant_id": str(town["rice"].pk), "quantity": "1"}
        assert (
            client.post(BASKET_URL, {**LOCATION, "items": [item, item]}, format="json").status_code
            == 400
        )

    def test_unknown_variant_is_400(self, town, login_as, make_user):
        client = login_as(make_user())
        body = {
            **LOCATION,
            "items": [{"variant_id": "00000000-0000-0000-0000-000000000000", "quantity": "1"}],
        }
        assert client.post(BASKET_URL, body, format="json").status_code == 400

    def test_default_mode_is_cost_benefit(self, town, login_as, make_user):
        fill(town)
        assert ask(login_as(make_user()), town)["mode"] == "MELHOR_CUSTO_BENEFICIO"
