"""Suggest catalog products for what was read. Suggestions only: the user picks."""

from dataclasses import dataclass

from django.db.models import Q

from apps.products.models import ProductVariant
from apps.products.normalization import normalize_text, parse_quantity

from .extraction import Extraction, Origin

MAX_SUGGESTIONS = 5
MIN_WORD_LEN = 3
MAX_WORDS = 12


@dataclass(frozen=True)
class VariantSuggestion:
    variant: ProductVariant
    basis: str  # "GTIN" (exact code read) or "TEXT" (words in common)
    origin: Origin
    score: float


def suggest_variants(extraction: Extraction) -> list[VariantSuggestion]:
    suggestions: dict[object, VariantSuggestion] = {}

    codes = [g.gtin for g in extraction.gtins]
    if codes:
        for variant in ProductVariant.objects.select_related("product__brand").filter(
            gtin__in=codes
        ):
            # The digits were read and verified; the catalog lookup is exact.
            suggestions[variant.pk] = VariantSuggestion(variant, "GTIN", Origin.FACT, 1.0)

    text = " ".join(extraction.name_lines)
    words = list(dict.fromkeys(w for w in normalize_text(text).split() if len(w) >= MIN_WORD_LEN))[
        :MAX_WORDS
    ]
    if words:
        match = Q()
        for word in words:
            match |= Q(product__normalized_name__contains=word) | Q(
                product__brand__normalized_name__contains=word
            )
        quantity = parse_quantity(text)
        candidates = ProductVariant.objects.select_related("product__brand").filter(match)[:200]
        for variant in candidates:
            if variant.pk in suggestions:
                continue
            haystack = f"{variant.product.normalized_name} " + (
                variant.product.brand.normalized_name if variant.product.brand else ""
            )
            hits = sum(1 for w in words if w in haystack)
            if hits < min(2, len(words)):
                continue
            score = hits / len(words)
            if quantity is not None and (
                variant.base_unit == quantity.base_unit
                and variant.base_quantity == quantity.base_amount
            ):
                score += 0.5
            suggestions[variant.pk] = VariantSuggestion(variant, "TEXT", Origin.INFERENCE, score)

    ranked = sorted(
        suggestions.values(),
        key=lambda s: (s.basis != "GTIN", -s.score, str(s.variant.product.normalized_name)),
    )
    return ranked[:MAX_SUGGESTIONS]
