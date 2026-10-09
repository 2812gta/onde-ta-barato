"""Turn the text the phone read from a price tag into candidates the user can confirm.

OCR runs on the device (ML Kit); the server only interprets the text. Every item says
whether it is a FACT (text actually present in what was read) or an INFERENCE (our
interpretation, e.g. which catalog product it probably is). Nothing here is ever recorded
as a price: only the user's explicit confirmation creates one.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from django.core.exceptions import ValidationError

from apps.core.validators import normalize_gtin

MAX_TEXT_CHARS = 5000
MAX_PRICE = Decimal("99999.99")


class Origin(StrEnum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"


@dataclass(frozen=True)
class PriceCandidate:
    value: Decimal
    raw: str  # exactly what was read, e.g. "R$ 24,90"
    line: int
    has_currency: bool
    origin: Origin = Origin.FACT


@dataclass(frozen=True)
class GtinCandidate:
    gtin: str  # normalized to 14 digits
    raw: str
    line: int
    origin: Origin = Origin.FACT  # the digits were read; the checksum was verified


@dataclass(frozen=True)
class Extraction:
    prices: list[PriceCandidate]
    gtins: list[GtinCandidate]
    name_lines: list[str]  # lines that are neither a price nor a barcode


# 24,90 | 1.249,90 | 24.90 (dot as decimal only when exactly two decimals follow)
_PRICE = re.compile(
    r"(?<![\d.,])(?P<cur>R\s*\$\s*)?(?P<int>\d{1,3}(?:\.\d{3})+|\d{1,5})[.,](?P<dec>\d{2})(?![\d])"
)
# "5,58/kg" is a unit price and "1,50 kg" a quantity: neither is the shelf price.
_UNIT_SUFFIX = re.compile(r"\s*(/|por\s|kg\b|g\b|ml\b|l\b|litro|un\b|und\b)", re.IGNORECASE)
_DIGIT_RUN = re.compile(r"(?<!\d)\d{8,14}(?!\d)")


def _parse_price(match: re.Match[str]) -> Decimal | None:
    integer = match.group("int").replace(".", "")
    try:
        value = Decimal(f"{integer}.{match.group('dec')}")
    except InvalidOperation:  # pragma: no cover - the pattern only admits digits
        return None
    return value if Decimal("0.01") <= value <= MAX_PRICE else None


def extract(text: str) -> Extraction:
    if len(text) > MAX_TEXT_CHARS:
        raise ValidationError("Texto lido grande demais.")
    prices: list[PriceCandidate] = []
    gtins: list[GtinCandidate] = []
    name_lines: list[str] = []
    seen_prices: set[tuple[Decimal, int]] = set()

    for index, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        consumed = stripped
        for run in _DIGIT_RUN.finditer(stripped):
            try:
                gtin = normalize_gtin(run.group())
            except ValidationError:
                continue
            gtins.append(GtinCandidate(gtin=gtin, raw=run.group(), line=index))
            consumed = consumed.replace(run.group(), " ")
        for match in _PRICE.finditer(stripped):
            if _UNIT_SUFFIX.match(stripped[match.end() :]):
                continue
            value = _parse_price(match)
            if value is None or (value, index) in seen_prices:
                continue
            seen_prices.add((value, index))
            prices.append(
                PriceCandidate(
                    value=value,
                    raw=match.group().strip(),
                    line=index,
                    has_currency=bool(match.group("cur")),
                )
            )
            consumed = consumed.replace(match.group(), " ")
        leftover = re.sub(r"\s+", " ", consumed).strip(" -–·|")
        if re.search(r"[A-Za-zÀ-ÿ]{3,}", leftover):
            name_lines.append(leftover)
    # Prices that carry "R$" come first: they are far more likely to be the shelf price.
    prices.sort(key=lambda p: (not p.has_currency, p.line))
    return Extraction(prices=prices, gtins=gtins, name_lines=name_lines)
