"""Tunable parameters of the cost-benefit algorithm. Defaults can be overridden with the
`RECOMMENDATION` setting. Every number here is a documented, reviewable assumption
(docs/RECOMMENDATIONS.md), not a hidden constant.

There is deliberately NO weight, bonus or input for anything commercial.
"""

from decimal import Decimal
from typing import Any

from django.conf import settings

ECONOMIZAR_MAIS = "ECONOMIZAR_MAIS"
MAIS_PROXIMO = "MAIS_PROXIMO"
MELHOR_CUSTO_BENEFICIO = "MELHOR_CUSTO_BENEFICIO"
MENOS_DESLOCAMENTO = "MENOS_DESLOCAMENTO"
MELHORES_PROMOCOES = "MELHORES_PROMOCOES"

MODES = (
    ECONOMIZAR_MAIS,
    MAIS_PROXIMO,
    MELHOR_CUSTO_BENEFICIO,
    MENOS_DESLOCAMENTO,
    MELHORES_PROMOCOES,
)

COMPONENTS = ("cost", "distance", "coverage", "promotions", "confidence")

DEFAULTS: dict[str, Any] = {
    # Money and distance
    "cost_per_km": Decimal("0.80"),  # R$ per km driven; the shopper may override (0 = on foot)
    "detour_factor": Decimal("1.3"),  # straight line underestimates real streets
    # Weights per mode; each row sums to 1.0
    "weights": {
        ECONOMIZAR_MAIS: {
            "cost": 0.70,
            "distance": 0.05,
            "coverage": 0.15,
            "promotions": 0.00,
            "confidence": 0.10,
        },
        MAIS_PROXIMO: {
            "cost": 0.15,
            "distance": 0.60,
            "coverage": 0.20,
            "promotions": 0.00,
            "confidence": 0.05,
        },
        MELHOR_CUSTO_BENEFICIO: {
            "cost": 0.40,
            "distance": 0.10,
            "coverage": 0.20,
            "promotions": 0.10,
            "confidence": 0.20,
        },
        MENOS_DESLOCAMENTO: {
            "cost": 0.20,
            "distance": 0.55,
            "coverage": 0.20,
            "promotions": 0.00,
            "confidence": 0.05,
        },
        MELHORES_PROMOCOES: {
            "cost": 0.25,
            "distance": 0.05,
            "coverage": 0.15,
            "promotions": 0.45,
            "confidence": 0.10,
        },
    },
    # A promotion share of the basket at or above this counts as a full promotions score
    "promo_full_score_share": 0.25,
    # Honesty thresholds
    "tie_margin": 0.02,  # scores closer than this are a tie, not a winner
    "min_coverage_for_comparison": 0.5,  # a store with less of the list cannot win a comparison
    "min_confidence": 0.35,  # below this average price confidence we refuse to recommend
    "conflict_confidence_factor": 0.7,  # confidence multiplier when sources disagree
    # Search size
    "pair_candidates": 8,  # stores considered when building two-store plans
    "max_stores_considered": 40,
    "fresh_hours": 24,  # "recent" price for the explanation
}


def get() -> dict[str, Any]:
    override = getattr(settings, "RECOMMENDATION", {})
    return {**DEFAULTS, **override}


def weights_for(mode: str) -> dict[str, float]:
    return dict(get()["weights"][mode])
