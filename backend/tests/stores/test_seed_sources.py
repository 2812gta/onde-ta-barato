"""Seed importers are tested offline with realistic payloads; no network in the test suite."""

import json
from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.products import openfoodfacts as off
from apps.products.models import CatalogSource, Category, ProductVariant
from apps.stores import osm
from apps.stores.models import Store, StoreSource, StoreType

OVERPASS = {
    "elements": [
        {
            "type": "node",
            "id": 1,
            "lat": -3.8767,
            "lon": -38.6256,
            "tags": {
                "shop": "supermarket",
                "name": "Supermercado Sol",
                "addr:street": "Rua A",
                "addr:housenumber": "100",
                "addr:postcode": "61900-000",
                "phone": "+55 85 3333-4444",
                "opening_hours": "Mo-Sa 07:00-21:00",
            },
        },
        {
            "type": "way",
            "id": 2,
            "center": {"lat": -3.88, "lon": -38.63},
            "tags": {"shop": "bakery", "name": "Padaria Doce"},
        },
        {
            "type": "node",
            "id": 3,
            "lat": -3.9,
            "lon": -38.6,
            "tags": {"shop": "supermarket"},
        },  # no name
        {"type": "node", "id": 4, "tags": {"shop": "supermarket", "name": "Sem coordenada"}},
        {
            "type": "node",
            "id": 5,
            "lat": -3.9,
            "lon": -38.6,
            "tags": {"shop": "clothes", "name": "Moda"},
        },
    ]
}


@pytest.mark.django_db
class TestOsmSeeding:
    def test_parse_keeps_only_named_located_food_shops(self):
        records = osm.parse(OVERPASS)
        assert [r.name for r in records] == ["Supermercado Sol", "Padaria Doce"]
        assert records[0].external_id == "node/1"
        assert records[1].external_id == "way/2"  # way uses its computed center
        assert records[1].lat == pytest.approx(-3.88)
        assert records[0].postal_code == "61900000"

    def test_import_creates_unclaimed_stores_with_source(self):
        result = osm.import_stores(osm.parse(OVERPASS))
        assert result == {"created": 2, "updated": 0, "skipped_claimed": 0}
        store = Store.objects.get(external_id="node/1")
        assert (store.source, store.merchant, store.store_type) == (
            StoreSource.OPENSTREETMAP,
            None,
            StoreType.SUPERMARKET,
        )
        assert store.opening_hours == {"osm": "Mo-Sa 07:00-21:00"}

    def test_import_is_idempotent(self):
        osm.import_stores(osm.parse(OVERPASS))
        result = osm.import_stores(osm.parse(OVERPASS))
        assert result == {"created": 0, "updated": 2, "skipped_claimed": 0}
        assert Store.objects.count() == 2

    def test_merchant_claimed_store_is_never_overwritten(self, make_merchant):
        osm.import_stores(osm.parse(OVERPASS))
        store = Store.objects.get(external_id="node/1")
        store.merchant = make_merchant()
        store.name = "Nome corrigido pelo dono"
        store.save()
        result = osm.import_stores(osm.parse(OVERPASS))
        store.refresh_from_db()
        assert store.name == "Nome corrigido pelo dono"
        assert result["skipped_claimed"] == 1

    def test_command_dry_run_writes_nothing(self, tmp_path, capsys):
        path = tmp_path / "overpass.json"
        path.write_text(json.dumps(OVERPASS), encoding="utf-8")
        call_command("import_osm_stores", file=str(path), dry_run=True)
        assert Store.objects.count() == 0
        assert "2 usable stores" in capsys.readouterr().out

    def test_command_imports_and_reminds_attribution(self, tmp_path, capsys):
        path = tmp_path / "overpass.json"
        path.write_text(json.dumps(OVERPASS), encoding="utf-8")
        call_command("import_osm_stores", file=str(path))
        out = capsys.readouterr().out
        assert Store.objects.count() == 2
        assert "OpenStreetMap contributors" in out

    def test_query_targets_only_food_shops_inside_bbox(self):
        query = osm.build_query((-4.2, -38.85, -3.6, -38.3))
        assert "supermarket" in query and "clothes" not in query
        assert "(-4.2,-38.85,-3.6,-38.3)" in query


OFF = [
    {
        "code": "7891000100103",
        "product_name": "Leite Condensado",
        "brands": "Moça,Nestlé",
        "quantity": "395 g",
        "categories_tags": ["en:dairies", "en:condensed-milks"],
    },
    {
        "code": "7891910000197",
        "product_name": "Açúcar Refinado",
        "product_name_pt": "Açúcar Refinado União",
        "brands": "União",
        "quantity": "1 kg",
        "categories_tags": ["en:sugars"],
    },
    {"code": "7891000100104", "product_name": "GTIN inválido", "quantity": "1 kg"},
    {"code": "40170725", "product_name": "", "quantity": "1 kg"},
    {"code": "036000291452", "product_name": "Sem quantidade", "quantity": ""},
    {
        "code": "12345678901231",
        "product_name": "Misterioso",
        "brands": "X",
        "quantity": "2 un",
        "categories_tags": ["en:unknown-things"],
    },
]


@pytest.mark.django_db
class TestOpenFoodFactsSeeding:
    def test_parse_skips_unusable_products_without_guessing(self):
        records = [r for r in (off.parse(p) for p in OFF) if r]
        assert [r.gtin for r in records] == ["07891000100103", "07891910000197", "12345678901231"]

    def test_parse_fields(self):
        milk = off.parse(OFF[0])
        assert (milk.brand, milk.quantity, milk.unit, milk.category_slug) == (
            "Moça",
            Decimal(395),
            "g",
            "laticinios",
        )
        assert off.parse(OFF[1]).name == "Açúcar Refinado União"  # prefers the Portuguese name

    def test_unknown_category_stays_empty_rather_than_guessed(self):
        assert off.parse(OFF[5]).category_slug is None

    def test_import_marks_source_and_is_idempotent(self):
        records = [r for r in (off.parse(p) for p in OFF) if r]
        first = off.import_products(records)
        second = off.import_products(records)
        assert first == {"created": 3, "existing": 0}
        assert second == {"created": 0, "existing": 3}
        variant = ProductVariant.objects.get(gtin="07891000100103")
        assert variant.catalog_source == CatalogSource.OPEN_FOOD_FACTS
        assert variant.product.category == Category.objects.get(slug="laticinios")
        assert variant.source_ref == "off:07891000100103"

    def test_command_with_file(self, tmp_path, capsys):
        path = tmp_path / "off.json"
        path.write_text(json.dumps(OFF), encoding="utf-8")
        call_command("import_off_products", file=str(path))
        out = capsys.readouterr().out
        assert ProductVariant.objects.count() == 3
        assert "Open Food Facts contributors" in out

    def test_command_requires_input(self):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError):
            call_command("import_off_products")
