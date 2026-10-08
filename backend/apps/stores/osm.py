"""OpenStreetMap store seeding (cold start).

Data © OpenStreetMap contributors, licensed under the ODbL (https://www.openstreetmap.org/copyright).
Attribution must be shown wherever these stores are displayed (see docs/DATA_SOURCES.md).
We never invent stores: a record needs a name and a coordinate from OSM itself.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from django.db import transaction

from .models import Store, StoreSource, StoreType
from .selectors import point_from

# Public instances are shared and often busy; try mirrors in order.
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
USER_AGENT = "OndeTaBarato/0.1 (store seeding; contact: genival.suporte@gmail.com)"

# Metropolitan region of Fortaleza (south, west, north, east).
DEFAULT_BBOX = (-4.20, -38.85, -3.60, -38.30)

SHOP_TYPES = {
    "supermarket": StoreType.SUPERMARKET,
    "convenience": StoreType.MINIMARKET,
    "wholesale": StoreType.WHOLESALE,
    "bakery": StoreType.BAKERY,
    "butcher": StoreType.BUTCHER,
    "greengrocer": StoreType.GREENGROCER,
}


@dataclass(frozen=True)
class OsmStore:
    external_id: str
    name: str
    store_type: str
    lat: float
    lon: float
    street: str = ""
    number: str = ""
    neighborhood: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    phone: str = ""
    opening_hours: str = ""


def build_query(bbox: tuple[float, float, float, float]) -> str:
    south, west, north, east = bbox
    shops = "|".join(SHOP_TYPES)
    return (
        f'[out:json][timeout:90];nwr["shop"~"^({shops})$"]({south},{west},{north},{east});'
        "out center tags;"
    )


class OverpassError(Exception):
    """No Overpass instance answered. Try again later or with a smaller --bbox."""


def fetch(bbox: tuple[float, float, float, float], timeout: int = 120) -> dict[str, Any]:
    body = urllib.parse.urlencode({"data": build_query(bbox)}).encode()
    errors = []
    for url in OVERPASS_URLS:
        request = urllib.request.Request(  # noqa: S310 - fixed https URLs
            url,
            data=body,
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            errors.append(f"{url}: {exc}")
    details = "\n  ".join(errors)
    raise OverpassError(f"All Overpass instances failed:\n  {details}")


def parse(payload: dict[str, Any]) -> list[OsmStore]:
    """Keep only elements with a name and a coordinate; everything else is skipped, not guessed."""
    stores = []
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        name = (tags.get("name") or "").strip()
        center = element if "lat" in element else element.get("center", {})
        shop = tags.get("shop", "")
        if not name or shop not in SHOP_TYPES or "lat" not in center or "lon" not in center:
            continue
        stores.append(
            OsmStore(
                external_id=f"{element['type']}/{element['id']}",
                name=name[:200],
                store_type=SHOP_TYPES[shop],
                lat=float(center["lat"]),
                lon=float(center["lon"]),
                street=tags.get("addr:street", "")[:200],
                number=tags.get("addr:housenumber", "")[:20],
                neighborhood=(tags.get("addr:suburb") or tags.get("addr:neighbourhood", ""))[:100],
                city=tags.get("addr:city", "")[:100],
                state=tags.get("addr:state", "")[:2],
                postal_code="".join(c for c in tags.get("addr:postcode", "") if c.isdigit())[:8],
                phone=(tags.get("phone") or tags.get("contact:phone", ""))[:30],
                opening_hours=tags.get("opening_hours", "")[:200],
            )
        )
    return stores


@transaction.atomic
def import_stores(records: list[OsmStore]) -> dict[str, int]:
    """Idempotent upsert keyed by OSM id. Stores claimed by a merchant are never overwritten."""
    created = updated = skipped_claimed = 0
    for record in records:
        existing = Store.all_objects.filter(
            source=StoreSource.OPENSTREETMAP, external_id=record.external_id
        ).first()
        values = {
            "name": record.name,
            "store_type": record.store_type,
            "location": point_from(record.lat, record.lon),
            "street": record.street,
            "number": record.number,
            "neighborhood": record.neighborhood,
            "city": record.city,
            "state": record.state,
            "postal_code": record.postal_code,
            "phone": record.phone,
            "opening_hours": {"osm": record.opening_hours} if record.opening_hours else {},
        }
        if existing is None:
            Store.objects.create(
                source=StoreSource.OPENSTREETMAP, external_id=record.external_id, **values
            )
            created += 1
        elif existing.merchant_id is not None:
            skipped_claimed += 1  # the merchant owns this data now
        else:
            for key, value in values.items():
                setattr(existing, key, value)
            existing.deleted_at = None
            existing.save()
            updated += 1
    return {"created": created, "updated": updated, "skipped_claimed": skipped_claimed}
