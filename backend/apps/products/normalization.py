"""Text and quantity normalization so spelling differences do not create duplicate products.

"ARROZ TIO JOÃO 5KG" and "Arroz Tio Joao 5 kg" must resolve to the same identity. These are
pure functions: no database, no AI. AI may suggest, but identity comes from rules we can test.
"""

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# Conservative: only abbreviations that are unambiguous in grocery labels.
_ABBREVIATIONS = {
    "tp": "tipo",
    "pct": "pacote",
    "cx": "caixa",
    "gr": "g",
    "grs": "g",
    "kgs": "kg",
    "mls": "ml",
    "lt": "l",
    "lts": "l",
    "und": "un",
    "unid": "un",
    "ud": "un",
}

# unit token -> (canonical unit)
_UNITS = {"kg": "kg", "g": "g", "ml": "ml", "l": "l", "un": "un", "m": "m"}

# (factor to base unit, base unit)
_BASE = {
    "kg": (Decimal(1000), "g"),
    "g": (Decimal(1), "g"),
    "l": (Decimal(1000), "ml"),
    "ml": (Decimal(1), "ml"),
    "un": (Decimal(1), "un"),
    "m": (Decimal(1), "m"),
}

_QUANTITY = re.compile(
    r"(?<![\w.,])(?:(?P<mult>\d{1,3})\s*x\s*)?(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<unit>[a-z]{1,4})\b"
)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_text(text: str) -> str:
    """Lowercase, no accents, punctuation collapsed to single spaces. Keeps decimal separators."""
    text = strip_accents(text or "").lower()
    text = re.sub(r"[^a-z0-9.,]+", " ", text)
    text = re.sub(r"(?<!\d)[.,]|[.,](?!\d)", " ", text)  # drop separators not inside numbers
    return re.sub(r"\s+", " ", text).strip()


def _expand(tokens: list[str]) -> list[str]:
    return [_ABBREVIATIONS.get(t, t) for t in tokens]


@dataclass(frozen=True)
class ParsedQuantity:
    amount: Decimal  # total amount in `unit` (multipacks already multiplied)
    unit: str  # canonical: kg, g, ml, l, un, m
    pack_count: int = 1

    @property
    def base_amount(self) -> Decimal:
        return self.amount * _BASE[self.unit][0]

    @property
    def base_unit(self) -> str:
        return _BASE[self.unit][1]


def to_base(amount: Decimal, unit: str) -> tuple[Decimal, str]:
    factor, base_unit = _BASE[unit]
    return amount * factor, base_unit


def parse_quantity(text: str) -> ParsedQuantity | None:
    """First quantity found in text: '5KG', '1,5 l', '12x350ml', '500 gr'."""
    cleaned = " ".join(_expand(normalize_text(text).split()))
    for match in _QUANTITY.finditer(cleaned):
        unit = _UNITS.get(match.group("unit"))
        if unit is None:
            continue
        try:
            amount = Decimal(match.group("amount").replace(",", "."))
        except InvalidOperation:
            continue
        if amount <= 0:
            continue
        mult = int(match.group("mult") or 1)
        return ParsedQuantity(amount=amount * mult, unit=unit, pack_count=mult)
    return None


@dataclass(frozen=True)
class ParsedProduct:
    name: str  # normalized, without brand and quantity
    brand: str | None  # normalized brand when one of the known brands was found
    quantity: ParsedQuantity | None


def parse_product_text(text: str, known_brands: list[str] | None = None) -> ParsedProduct:
    """Split free text (OCR line, shelf label) into name / brand / quantity.

    The brand is only recognised from `known_brands`; we never guess a brand.
    """
    normalized = " ".join(_expand(normalize_text(text).split()))
    quantity = parse_quantity(normalized)
    if quantity is not None:
        match = next(_QUANTITY.finditer(normalized))
        normalized = (normalized[: match.start()] + " " + normalized[match.end() :]).strip()
    brand = None
    for candidate in sorted(known_brands or [], key=len, reverse=True):
        norm_brand = normalize_text(candidate)
        pattern = rf"(?<!\w){re.escape(norm_brand)}(?!\w)"
        if norm_brand and re.search(pattern, normalized):
            brand = norm_brand
            normalized = re.sub(pattern, " ", normalized, count=1)
            break
    return ParsedProduct(
        name=re.sub(r"\s+", " ", normalized).strip(), brand=brand, quantity=quantity
    )
