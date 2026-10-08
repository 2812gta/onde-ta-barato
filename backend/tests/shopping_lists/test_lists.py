import pytest

from apps.shopping_lists import services
from apps.shopping_lists.models import ShoppingList, ShoppingListItem
from tests.conftest import PASSWORD

LISTS = "/api/v1/shopping-lists/"


def detail(list_id):
    return f"{LISTS}{list_id}/"


def items_url(list_id):
    return f"{LISTS}{list_id}/items/"


@pytest.fixture
def shopper(make_user, login_as):
    user = make_user()
    return user, login_as(user)


@pytest.mark.django_db
class TestLists:
    def test_requires_login(self, api):
        assert api.get(LISTS).status_code == 401
        assert api.post(LISTS, {"name": "x"}, format="json").status_code == 401

    def test_create_list_and_see_it(self, shopper):
        _, client = shopper
        created = client.post(LISTS, {"name": "  Compras   da semana "}, format="json")
        assert created.status_code == 201
        assert created.json()["name"] == "Compras da semana"  # whitespace collapsed
        rows = client.get(LISTS).json()
        assert [r["name"] for r in rows] == ["Compras da semana"]
        assert rows[0]["item_count"] == 0

    def test_blank_name_is_rejected(self, shopper):
        _, client = shopper
        assert client.post(LISTS, {"name": "   "}, format="json").status_code == 400
        assert client.post(LISTS, {}, format="json").status_code == 400

    def test_rename_and_delete(self, shopper):
        user, client = shopper
        pk = client.post(LISTS, {"name": "A"}, format="json").json()["id"]
        assert client.patch(detail(pk), {"name": "B"}, format="json").json()["name"] == "B"
        assert client.delete(detail(pk)).status_code == 204
        assert not ShoppingList.objects.filter(user=user).exists()
        assert client.get(detail(pk)).status_code == 404

    def test_list_limit(self, make_user):
        user = make_user()
        for n in range(services.MAX_LISTS):
            services.create_list(user=user, name=f"L{n}")
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            services.create_list(user=user, name="uma a mais")


@pytest.mark.django_db
class TestOwnership:
    """Another shopper's list must look like it does not exist."""

    def test_other_users_data_is_invisible_and_untouchable(self, make_user, login_as, make_variant):
        owner = make_user()
        shopping_list = services.create_list(user=owner, name="Privada")
        item = services.add_item(shopping_list=shopping_list, variant=make_variant(), quantity=2)
        intruder = login_as(make_user())
        assert intruder.get(LISTS).json() == []
        assert intruder.get(detail(shopping_list.pk)).status_code == 404
        assert (
            intruder.patch(detail(shopping_list.pk), {"name": "x"}, format="json").status_code
            == 404
        )
        assert intruder.delete(detail(shopping_list.pk)).status_code == 404
        assert intruder.post(items_url(shopping_list.pk), {}, format="json").status_code == 404
        item_url = f"{items_url(shopping_list.pk)}{item.pk}/"
        assert intruder.patch(item_url, {"checked": True}, format="json").status_code == 404
        assert intruder.delete(item_url).status_code == 404
        item.refresh_from_db()
        assert item.checked is False and ShoppingList.objects.filter(pk=shopping_list.pk).exists()


@pytest.mark.django_db
class TestItems:
    def test_add_update_check_remove(self, shopper, make_variant):
        _, client = shopper
        pk = client.post(LISTS, {"name": "Mês"}, format="json").json()["id"]
        variant = make_variant()
        added = client.post(
            items_url(pk), {"variant_id": str(variant.pk), "quantity": "2"}, format="json"
        )
        assert added.status_code == 201
        body = added.json()
        assert body["label"] == "Arroz Tio João 5 kg" and body["quantity"] == "2.000"
        url = f"{items_url(pk)}{body['id']}/"
        assert client.patch(url, {"quantity": "3.5"}, format="json").json()["quantity"] == "3.500"
        assert client.patch(url, {"checked": True}, format="json").json()["checked"] is True
        summary = client.get(LISTS).json()[0]
        assert summary["item_count"] == 1 and summary["checked_count"] == 1
        assert client.delete(url).status_code == 204
        assert client.get(detail(pk)).json()["items"] == []

    def test_adding_the_same_product_adds_up(self, shopper, make_variant):
        _, client = shopper
        pk = client.post(LISTS, {"name": "L"}, format="json").json()["id"]
        variant = make_variant()
        body = {"variant_id": str(variant.pk), "quantity": "2"}
        client.post(items_url(pk), body, format="json")
        client.post(items_url(pk), body, format="json")
        items = client.get(detail(pk)).json()["items"]
        assert len(items) == 1 and items[0]["quantity"] == "4.000"

    @pytest.mark.parametrize("quantity", ["0", "-1", "1000.001", "abc"])
    def test_bad_quantity(self, shopper, make_variant, quantity):
        _, client = shopper
        pk = client.post(LISTS, {"name": "L"}, format="json").json()["id"]
        response = client.post(
            items_url(pk),
            {"variant_id": str(make_variant().pk), "quantity": quantity},
            format="json",
        )
        assert response.status_code == 400
        assert not ShoppingListItem.objects.exists()

    def test_unknown_product(self, shopper):
        _, client = shopper
        pk = client.post(LISTS, {"name": "L"}, format="json").json()["id"]
        bad = {"variant_id": "00000000-0000-0000-0000-000000000000"}
        assert client.post(items_url(pk), bad, format="json").status_code == 400

    def test_item_limit(self, make_user, make_variant, monkeypatch):
        from django.core.exceptions import ValidationError

        monkeypatch.setattr(services, "MAX_ITEMS", 2)
        shopping_list = services.create_list(user=make_user(), name="L")
        services.add_item(shopping_list=shopping_list, variant=make_variant(), quantity=1)
        services.add_item(
            shopping_list=shopping_list, variant=make_variant(name="Feijão", brand="X"), quantity=1
        )
        with pytest.raises(ValidationError):
            services.add_item(
                shopping_list=shopping_list,
                variant=make_variant(name="Açúcar", brand="Y"),
                quantity=1,
            )
        # topping up a product already on the list is not a new item
        services.add_item(shopping_list=shopping_list, variant=make_variant(), quantity=1)

    def test_a_list_holds_no_prices(self, shopper, make_variant):
        _, client = shopper
        pk = client.post(LISTS, {"name": "L"}, format="json").json()["id"]
        client.post(items_url(pk), {"variant_id": str(make_variant().pk)}, format="json")
        item = client.get(detail(pk)).json()["items"][0]
        assert not {"price", "unit_price", "total"} & set(item)


@pytest.mark.django_db
class TestLgpd:
    def test_deleting_the_account_erases_lists(self, make_user, login_as, make_variant):
        user = make_user()
        shopping_list = services.create_list(user=user, name="Minha")
        services.add_item(shopping_list=shopping_list, variant=make_variant(), quantity=1)
        client = login_as(user)
        export = client.get("/api/v1/me/export/")
        assert export.status_code == 200
        assert export.json()["shopping_lists"][0]["name"] == "Minha"
        assert (
            client.delete("/api/v1/me/", {"password": PASSWORD}, format="json").status_code == 204
        )
        assert not ShoppingList.objects.exists() and not ShoppingListItem.objects.exists()
