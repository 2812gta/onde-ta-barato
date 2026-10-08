"""The cart prices a shopping trip at one store with the same honesty rules as recommendations."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.merchants.models import Merchant, VerificationStatus
from apps.prices.models import PriceObservation
from apps.promotions import services as promotion_services
from apps.shopping_cart import services
from apps.shopping_cart.models import CartItem, CartStatus, ShoppingCart
from apps.shopping_lists import services as list_services
from tests.conftest import MARACANAU, PASSWORD

CART = "/api/v1/shopping-cart/"
RULE = {"type": "FIXED_PRICE", "bundle_quantity": 3, "bundle_price": "20.00"}


def add_price(store, variant, value, *, hours_ago=1, source="MERCHANT", condition="NORMAL"):
    return PriceObservation.objects.create(
        product_variant=variant,
        store=store,
        price=Decimal(value),
        source=source,
        payment_condition=condition,
        collected_at=timezone.now() - timedelta(hours=hours_ago),
        confidence_score=Decimal("0.6"),
        confidence_level="MEDIUM",
    )


@pytest.fixture
def world(make_user, make_merchant, make_store, make_variant):
    owner = make_user()
    merchant = make_merchant(owner=owner, verified=True, trade_name="Verificado")
    store = make_store(merchant=merchant, coords=MARACANAU, name="Loja Cesta")
    return {
        "owner": owner,
        "merchant": merchant,
        "store": store,
        "rice": make_variant(),
        "beans": make_variant(name="Feijão Carioca", brand="Camil", quantity="1", unit="kg"),
    }


@pytest.fixture
def shopper(make_user, login_as):
    user = make_user()
    return user, login_as(user)


def put_store(client, store, **extra):
    response = client.put(CART, {"store_id": str(store.pk), **extra}, format="json")
    assert response.status_code == 200, response.content
    return response.json()


def add(client, variant, quantity="1"):
    response = client.post(
        CART + "items/", {"variant_id": str(variant.pk), "quantity": quantity}, format="json"
    )
    assert response.status_code == 201, response.content
    return response.json()


@pytest.mark.django_db
class TestBasics:
    def test_requires_login(self, api):
        assert api.get(CART).status_code == 401
        assert api.post(CART + "close/").status_code == 401

    def test_reading_never_creates_a_cart(self, shopper):
        _, client = shopper
        data = client.get(CART).json()
        assert data["id"] is None and data["items"] == [] and data["totals"]["total"] == "0.00"
        assert not ShoppingCart.objects.exists()

    def test_one_open_cart_per_user(self, shopper, world):
        user, client = shopper
        put_store(client, world["store"])
        add(client, world["rice"])
        assert ShoppingCart.objects.filter(user=user, status=CartStatus.OPEN).count() == 1

    def test_item_without_a_store_is_listed_but_unpriced(self, shopper, world):
        _, client = shopper
        data = add(client, world["rice"], "2")
        assert data["items"][0]["priced"] is False and data["store"] is None
        assert data["totals"]["unpriced_count"] == 1
        assert "Escolha o mercado" in data["warnings"][0]

    def test_bad_store_and_payment(self, shopper):
        _, client = shopper
        none = {"store_id": "00000000-0000-0000-0000-000000000000"}
        assert client.put(CART, none, format="json").status_code == 400
        assert client.put(CART, {"payment_condition": "BITCOIN"}, format="json").status_code == 400


@pytest.mark.django_db
class TestPricing:
    def test_totals_use_the_stores_current_price(self, shopper, world):
        _, client = shopper
        add_price(world["store"], world["rice"], "24.00")
        add_price(world["store"], world["beans"], "6.50")
        put_store(client, world["store"])
        add(client, world["rice"], "1")
        data = add(client, world["beans"], "2")
        by_label = {i["label"]: i for i in data["items"]}
        assert by_label["Arroz Tio João 5 kg"]["net"] == "24.00"
        assert by_label["Feijão Carioca 1 kg"]["gross"] == "13.00"
        assert data["totals"]["total"] == "37.00" and data["totals"]["savings"] == "0.00"
        assert "Os preços podem divergir do caixa." in data["warnings"]

    def test_item_without_a_price_stays_out_of_the_total(self, shopper, world):
        _, client = shopper
        add_price(world["store"], world["rice"], "24.00")
        put_store(client, world["store"])
        add(client, world["rice"])
        data = add(client, world["beans"])
        beans = next(i for i in data["items"] if "Feijão" in i["label"])
        assert beans["priced"] is False and beans["net"] is None
        assert data["totals"]["total"] == "24.00" and data["totals"]["unpriced_count"] == 1
        assert any("sem preço atual" in w for w in data["warnings"])

    def test_a_price_older_than_the_listing_horizon_is_not_used(self, shopper, world):
        _, client = shopper
        add_price(world["store"], world["rice"], "1.00", hours_ago=24 * 120)
        put_store(client, world["store"])
        data = add(client, world["rice"])
        assert data["items"][0]["priced"] is False

    def test_stale_price_is_used_but_flagged(self, shopper, world):
        _, client = shopper
        add_price(world["store"], world["rice"], "24.00", hours_ago=300)  # mercearia ttl is 240h
        put_store(client, world["store"])
        data = add(client, world["rice"])
        line = data["items"][0]
        assert line["priced"] and line["freshness"] != "CURRENT"
        assert "Alguns preços estão desatualizados." in data["warnings"]

    def test_conflicting_sources_use_the_higher_price(self, shopper, world, make_user):
        _, client = shopper
        add_price(world["store"], world["rice"], "24.00")
        add_price(world["store"], world["rice"], "12.00", source="USER")
        put_store(client, world["store"])
        data = add(client, world["rice"])
        line = data["items"][0]
        assert line["conflict"] is True  # 24.00 vs 12.00 is far beyond the 1% tolerance
        assert line["unit_price"] == "24.00"  # never promise the lower price we cannot back
        assert any("divergentes" in w for w in data["warnings"])

    def test_pix_price_only_for_pix_shoppers(self, shopper, world):
        _, client = shopper
        add_price(world["store"], world["rice"], "25.00")
        add_price(world["store"], world["rice"], "22.00", condition="PIX")
        put_store(client, world["store"])
        card = add(client, world["rice"])
        assert card["items"][0]["unit_price"] == "25.00"
        pix = put_store(client, world["store"], payment_condition="PIX")
        assert pix["items"][0]["unit_price"] == "22.00" and pix["totals"]["total"] == "22.00"

    def test_a_verified_merchants_promotion_changes_the_total(self, shopper, world):
        _, client = shopper
        add_price(world["store"], world["rice"], "10.00")
        promotion_services.create_promotion(
            store=world["store"],
            actor=world["owner"],
            variant=world["rice"],
            title="3 por R$ 20",
            rule=RULE,
        )
        put_store(client, world["store"])
        data = add(client, world["rice"], "5")
        line = data["items"][0]
        assert line["gross"] == "50.00" and line["net"] == "40.00"  # 3 for 20 + 2 x 10
        assert line["promotion"] == "3 por R$ 20" and data["totals"]["savings"] == "10.00"

    def test_an_unverified_merchants_promotion_is_only_reported(self, shopper, world):
        _, client = shopper
        add_price(world["store"], world["rice"], "10.00")
        promotion_services.create_promotion(
            store=world["store"],
            actor=world["owner"],
            variant=world["rice"],
            title="3 por R$ 20",
            rule=RULE,
        )
        Merchant.objects.filter(pk=world["merchant"].pk).update(status=VerificationStatus.PENDING)
        put_store(client, world["store"])
        data = add(client, world["rice"], "5")
        line = data["items"][0]
        assert line["net"] == "50.00" and line["promotion"] is None  # NOT applied
        assert line["unconfirmed_potential"] == "10.00"
        assert data["totals"]["total"] == "50.00"
        assert data["totals"]["unconfirmed_potential"] == "10.00"

    def test_prices_are_computed_on_read_not_stored(self, shopper, world):
        _, client = shopper
        add_price(world["store"], world["rice"], "24.00", hours_ago=2)
        put_store(client, world["store"])
        add(client, world["rice"])
        add_price(world["store"], world["rice"], "21.00", hours_ago=1)
        assert client.get(CART).json()["totals"]["total"] == "21.00"


@pytest.mark.django_db
class TestItems:
    def test_same_product_adds_up_and_quantity_can_change(self, shopper, world):
        _, client = shopper
        add(client, world["rice"], "2")
        data = add(client, world["rice"], "1")
        assert len(data["items"]) == 1 and data["items"][0]["quantity"] == "3.000"
        item_id = data["items"][0]["id"]
        patched = client.patch(
            f"{CART}items/{item_id}/", {"quantity": "1", "in_basket": True}, format="json"
        ).json()
        assert patched["items"][0]["quantity"] == "1.000" and patched["items"][0]["in_basket"]
        removed = client.delete(f"{CART}items/{item_id}/").json()
        assert removed["items"] == []

    @pytest.mark.parametrize("quantity", ["0", "-2", "1001"])
    def test_bad_quantity(self, shopper, world, quantity):
        _, client = shopper
        response = client.post(
            CART + "items/",
            {"variant_id": str(world["rice"].pk), "quantity": quantity},
            format="json",
        )
        assert response.status_code == 400

    def test_cart_item_limit(self, make_user, world, monkeypatch):
        monkeypatch.setattr(services, "MAX_ITEMS", 1)
        cart = services.get_or_open_cart(make_user())
        services.add_item(cart=cart, variant=world["rice"], quantity=Decimal(1))
        with pytest.raises(ValidationError):
            services.add_item(cart=cart, variant=world["beans"], quantity=Decimal(1))

    def test_other_shoppers_items_do_not_exist(self, shopper, world, make_user, login_as):
        _, client = shopper
        item_id = add(client, world["rice"])["items"][0]["id"]
        intruder = login_as(make_user())
        assert (
            intruder.patch(f"{CART}items/{item_id}/", {"quantity": "9"}, format="json").status_code
            == 404
        )
        assert intruder.delete(f"{CART}items/{item_id}/").status_code == 404
        # `login_as` reuses one APIClient, so check the owner's data straight from the database
        assert CartItem.objects.get(pk=item_id).quantity == Decimal("1")


@pytest.mark.django_db
class TestImportAndClose:
    def test_import_a_list(self, shopper, world):
        user, client = shopper
        shopping_list = list_services.create_list(user=user, name="Semana")
        list_services.add_item(
            shopping_list=shopping_list, variant=world["rice"], quantity=Decimal(2)
        )
        list_services.add_item(
            shopping_list=shopping_list, variant=world["beans"], quantity=Decimal(3)
        )
        add(client, world["rice"], "1")
        data = client.post(
            CART + "import-list/", {"list_id": str(shopping_list.pk)}, format="json"
        ).json()
        quantities = {i["label"]: i["quantity"] for i in data["items"]}
        assert quantities == {"Arroz Tio João 5 kg": "3.000", "Feijão Carioca 1 kg": "3.000"}
        assert shopping_list.items.count() == 2  # the list itself is untouched

    def test_cannot_import_someone_elses_list(self, shopper, world, make_user):
        _, client = shopper
        other = list_services.create_list(user=make_user(), name="Alheia")
        list_services.add_item(shopping_list=other, variant=world["rice"], quantity=Decimal(1))
        response = client.post(CART + "import-list/", {"list_id": str(other.pk)}, format="json")
        assert response.status_code == 404
        assert client.get(CART).json()["items"] == []

    def test_closing_keeps_the_final_totals_and_frees_the_cart(self, shopper, world):
        user, client = shopper
        add_price(world["store"], world["rice"], "10.00")
        promotion_services.create_promotion(
            store=world["store"],
            actor=world["owner"],
            variant=world["rice"],
            title="3 por R$ 20",
            rule=RULE,
        )
        put_store(client, world["store"])
        add(client, world["rice"], "5")
        closed = client.post(CART + "close/").json()
        assert closed["totals"]["total"] == "40.00" and closed["status"] == CartStatus.CLOSED
        cart = ShoppingCart.objects.get(user=user)
        assert cart.final_total == Decimal("40.00") and cart.final_savings == Decimal("10.00")
        assert cart.closed_at is not None
        assert client.get(CART).json()["id"] is None  # a fresh trip starts empty
        add(client, world["beans"])
        assert ShoppingCart.objects.filter(user=user).count() == 2

    def test_cannot_close_an_empty_or_missing_cart(self, shopper, world):
        _, client = shopper
        assert client.post(CART + "close/").status_code == 404
        put_store(client, world["store"])
        assert client.post(CART + "close/").status_code == 400

    def test_closed_cart_items_cannot_be_changed(self, shopper, world):
        _, client = shopper
        item_id = add(client, world["rice"])["items"][0]["id"]
        client.post(CART + "close/")
        assert (
            client.patch(f"{CART}items/{item_id}/", {"quantity": "5"}, format="json").status_code
            == 404
        )


@pytest.mark.django_db
class TestLgpd:
    def test_deleting_the_account_erases_carts(self, make_user, login_as, world):
        user = make_user()
        client = login_as(user)
        add(client, world["rice"])
        assert ShoppingCart.objects.filter(user=user).exists()
        assert (
            client.delete("/api/v1/me/", {"password": PASSWORD}, format="json").status_code == 204
        )
        assert not ShoppingCart.objects.exists()
