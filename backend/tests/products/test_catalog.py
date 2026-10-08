from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.audit.models import AuditLog
from apps.products.models import Brand, Product, ProductVariant
from apps.products.services import get_or_create_variant
from apps.users.models import Role


@pytest.mark.django_db
class TestVariantIdentity:
    def test_creates_product_brand_and_variant(self, make_variant):
        variant = make_variant()
        assert variant.product.name == "Arroz Tio João"
        assert variant.product.brand.normalized_name == "tio joao"
        assert (variant.base_quantity, variant.base_unit) == (Decimal(5000), "g")

    def test_spelling_differences_do_not_create_duplicates(self, make_variant):
        a = make_variant(name="ARROZ TIO JOÃO", brand="TIO JOÃO", quantity="5", unit="kg")
        b = make_variant(name="Arroz  Tio Joao", brand="Tio Joao", quantity="5", unit="kg")
        assert a.pk == b.pk
        assert Product.objects.count() == 1
        assert Brand.objects.count() == 1

    def test_equivalent_units_are_the_same_presentation(self, make_variant):
        assert (
            make_variant(quantity="1", unit="kg").pk == make_variant(quantity="1000", unit="g").pk
        )

    def test_different_sizes_are_different_variants_of_one_product(self, make_variant):
        a = make_variant(quantity="1", unit="kg")
        b = make_variant(quantity="5", unit="kg")
        assert a.pk != b.pk
        assert a.product_id == b.product_id

    def test_gtin_is_normalized_and_found_again(self, make_variant):
        a = make_variant(gtin="7891000100103")
        found, created = get_or_create_variant(
            name="Qualquer nome", quantity=Decimal(1), unit="un", gtin="07891000100103"
        )
        assert created is False
        assert found.pk == a.pk
        assert a.gtin == "07891000100103"

    def test_gtin_learned_later_is_attached_without_duplicating(self, make_variant):
        original = make_variant()
        assert original.gtin is None
        again = make_variant(gtin="7891000100103")
        original.refresh_from_db()
        assert again.pk == original.pk
        assert original.gtin == "07891000100103"
        assert AuditLog.objects.filter(action="catalog.gtin_assigned").exists()

    def test_conflicting_gtin_for_same_presentation_is_refused(self, make_variant):
        make_variant(gtin="7891000100103")
        with pytest.raises(ValidationError):
            make_variant(gtin="7891910000197")

    def test_invalid_gtin_is_refused(self, make_variant):
        with pytest.raises(ValidationError):
            make_variant(gtin="7891000100104")

    def test_non_positive_quantity_is_refused(self, make_variant):
        with pytest.raises(ValidationError):
            make_variant(quantity="0")

    def test_soft_deleted_variant_frees_its_identity(self, make_variant):
        variant = make_variant(gtin="7891000100103")
        variant.delete()
        assert ProductVariant.objects.count() == 0
        assert ProductVariant.all_objects.count() == 1
        again = make_variant(gtin="7891000100103")
        assert again.pk != variant.pk


@pytest.mark.django_db
class TestCatalogApi:
    def test_categories_are_seeded_with_ttls(self, make_user, login_as):
        client = login_as(make_user())
        data = {c["slug"]: c["price_ttl_hours"] for c in client.get("/api/v1/categories/").json()}
        assert len(data) == 12
        assert data["hortifruti"] < data["mercearia"]  # fresh produce expires sooner

    def test_search_is_accent_and_order_insensitive(self, make_user, login_as, make_variant):
        make_variant()
        make_variant(name="Feijão Carioca", brand="Camil", quantity="1", unit="kg")
        client = login_as(make_user())
        for query in ["arroz", "TIO JOAO", "joão arroz", "camil feijao"]:
            results = client.get("/api/v1/variants/", {"q": query}).json()["results"]
            assert len(results) == 1, query

    def test_search_by_gtin_accepts_ean13_or_gtin14(self, make_user, login_as, make_variant):
        make_variant(gtin="7891000100103")
        client = login_as(make_user())
        for code in ["7891000100103", "07891000100103", "789.1000.100103"]:
            assert len(client.get("/api/v1/variants/", {"gtin": code}).json()["results"]) == 1

    def test_requires_authentication(self, api, db):
        assert api.get("/api/v1/variants/").status_code == 401

    def test_consumer_cannot_write_catalog(self, make_user, login_as):
        client = login_as(make_user())
        response = client.post(
            "/api/v1/catalog/variants/",
            {"name": "X", "quantity": "1", "unit": "kg"},
            format="json",
        )
        assert response.status_code == 403

    def test_merchant_creates_then_gets_existing(self, make_user, login_as, category):
        user = make_user(role=Role.MERCHANT_OWNER)
        client = login_as(user)
        body = {
            "name": "Feijão Carioca",
            "brand": "Camil",
            "category": category.slug,
            "quantity": "1",
            "unit": "kg",
            "gtin": "7891910000197",
        }
        first = client.post("/api/v1/catalog/variants/", body, format="json")
        second = client.post("/api/v1/catalog/variants/", body, format="json")
        assert (first.status_code, first.json()["created"]) == (201, True)
        assert (second.status_code, second.json()["created"]) == (200, False)
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["catalog_source"] == "MERCHANT"

    def test_invalid_gtin_is_a_400_not_a_500(self, make_user, login_as):
        client = login_as(make_user(role=Role.MERCHANT_OWNER))
        response = client.post(
            "/api/v1/catalog/variants/",
            {"name": "X", "quantity": "1", "unit": "kg", "gtin": "123"},
            format="json",
        )
        assert response.status_code == 400
