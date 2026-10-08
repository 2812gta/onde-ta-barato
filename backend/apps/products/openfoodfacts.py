"""Open Food Facts product seeding (cold start).

Data from Open Food Facts (https://world.openfoodfacts.org) is available under the Open
Database License (ODbL); attribution is required (see docs/DATA_SOURCES.md). We import text
facts only (name, brand, quantity, GTIN). Images are NOT imported: they carry separate licenses.
We never fabricate a field: a product without a valid GTIN, name or parsable quantity is skipped.
"""

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError

from apps.core.validators import normalize_gtin

from .models import CatalogSource, Category, ProductVariant
from .normalization import parse_quantity
from .services import get_or_create_variant

API = "https://world.openfoodfacts.org/api/v2"
USER_AGENT = "OndeTaBarato/0.1 (catalog seeding; contact: genival.suporte@gmail.com)"
FIELDS = "code,product_name,product_name_pt,brands,quantity,categories_tags"

# Only unambiguous keyword matches. No match -> no category (never a guess).
CATEGORY_KEYWORDS = {
    "bebidas": ("beverages", "bebidas", "waters", "sodas", "juices"),
    "laticinios": ("dairies", "laticinios", "milks", "cheeses", "yogurts"),
    "carnes-e-frios": ("meats", "carnes", "sausages", "hams"),
    "hortifruti": ("fruits-and-vegetables", "fresh-fruits", "fresh-vegetables"),
    "padaria": ("breads", "pães", "paes", "biscuits-and-cakes"),
    "congelados": ("frozen-foods", "congelados"),
    "mercearia": ("cereals-and-potatoes", "legumes", "rice", "pasta", "sugars", "oils", "canned"),
}


@dataclass(frozen=True)
class OffProduct:
    gtin: str
    name: str
    brand: str
    quantity: Decimal
    unit: str
    category_slug: str | None


def get_json(url: str, timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.load(response)


def fetch_by_gtin(gtin: str) -> dict[str, Any] | None:
    payload = get_json(f"{API}/product/{urllib.parse.quote(gtin)}.json?fields={FIELDS}")
    return payload.get("product") if payload.get("status") == 1 else None


def search(term: str, limit: int = 20) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {"search_terms": term, "countries_tags_en": "brazil", "page_size": limit, "fields": FIELDS}
    )
    return get_json(f"{API}/search?{query}").get("products", [])


def guess_category(tags: list[str]) -> str | None:
    joined = " ".join(tags).lower()
    for slug, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in joined for keyword in keywords):
            return slug
    return None


def parse(product: dict[str, Any]) -> OffProduct | None:
    try:
        gtin = normalize_gtin(str(product.get("code", "")))
    except ValidationError:
        return None
    name = (product.get("product_name_pt") or product.get("product_name") or "").strip()
    quantity = parse_quantity(product.get("quantity", ""))
    if not name or quantity is None:
        return None
    brand = (product.get("brands") or "").split(",")[0].strip()
    return OffProduct(
        gtin=gtin,
        name=name[:200],
        brand=brand[:120],
        quantity=quantity.amount,
        unit=quantity.unit,
        category_slug=guess_category(product.get("categories_tags", [])),
    )


def import_products(records: list[OffProduct]) -> dict[str, int]:
    created = existing = 0
    categories = {c.slug: c for c in Category.objects.all()}
    for record in records:
        if ProductVariant.objects.filter(gtin=record.gtin).exists():
            existing += 1
            continue
        _, was_created = get_or_create_variant(
            name=record.name,
            brand_name=record.brand,
            quantity=record.quantity,
            unit=record.unit,
            category=categories.get(record.category_slug or ""),
            gtin=record.gtin,
            source=CatalogSource.OPEN_FOOD_FACTS,
            source_ref=f"off:{record.gtin}",
        )
        created += int(was_created)
        existing += int(not was_created)
    return {"created": created, "existing": existing}
