"""Price confidence: an explainable score in [0, 1], not a black box.

    score = base(source, merchant_verified) * freshness(age / ttl)
            + evidence_bonus + location_bonus
            + min(confirmations * confirmation_step, confirmation_cap)
            - min(contradictions * contradiction_step, contradiction_cap)
            + (reputation - 0.5) * reputation_weight
    clamped to [0, 1]; LOW < 0.35 <= MEDIUM < 0.65 <= HIGH
    A USER price without evidence is capped just below HIGH, whatever its votes or location.

Vote COUNT alone never decides: a source has a base score, votes are capped, and every
vote must come from a user other than the author. Weights are configurable through the
`PRICE_CONFIDENCE` setting. Nothing here receives commercial data (plans, ads, payments):
see tests/prices/test_confidence.py::test_inputs_exclude_commercial_fields.
"""

from dataclasses import dataclass, field, fields
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.conf import settings

DEFAULTS: dict[str, Any] = {
    "base": {
        "MERCHANT_VERIFIED": 0.70,
        "MERCHANT": 0.55,
        "USER": 0.40,
        "FLYER": 0.65,
        "PUBLIC_SOURCE": 0.60,
        "HISTORICAL": 0.30,
        "CALCULATED": 0.25,
    },
    "evidence_bonus": 0.10,
    "location_bonus": 0.05,
    "confirmation_step": 0.08,
    "confirmation_cap": 0.24,
    "contradiction_step": 0.10,
    "contradiction_cap": 0.30,
    "reputation_weight": 0.20,
    "low_below": 0.35,
    "high_from": 0.65,
}


def weights() -> dict[str, Any]:
    return {**DEFAULTS, **getattr(settings, "PRICE_CONFIDENCE", {})}


@dataclass(frozen=True)
class ConfidenceInput:
    source: str
    age_hours: float
    ttl_hours: float
    has_evidence: bool = False
    confirmations: int = 0
    contradictions: int = 0
    merchant_verified: bool = False
    location_verified: bool = False
    contributor_reputation: float = 0.5  # 0..1; 0.5 = neutral/unknown
    # Deliberately no plan, payment, sponsorship or advertising fields.


@dataclass(frozen=True)
class Confidence:
    score: Decimal
    level: str
    factors: dict[str, float] = field(default_factory=dict)  # explanation shown to users


def freshness_factor(age_hours: float, ttl_hours: float) -> float:
    """1.0 while young, 0.6 at the TTL, 0.2 at twice the TTL, floor 0.1."""
    if ttl_hours <= 0:
        return 0.1
    ratio = max(age_hours, 0) / ttl_hours
    if ratio <= 0.5:
        return 1.0
    if ratio <= 1:
        return 1.0 - (ratio - 0.5) * 0.8
    if ratio <= 2:
        return 0.6 - (ratio - 1) * 0.4
    return 0.1


def level_for(score: float, w: dict[str, Any] | None = None) -> str:
    w = w or weights()
    if score < w["low_below"]:
        return "LOW"
    return "HIGH" if score >= w["high_from"] else "MEDIUM"


def compute_confidence(data: ConfidenceInput) -> Confidence:
    w = weights()
    base_key = (
        "MERCHANT_VERIFIED" if data.source == "MERCHANT" and data.merchant_verified else data.source
    )
    base = w["base"][base_key]
    fresh = freshness_factor(data.age_hours, data.ttl_hours)
    factors = {
        "base": base,
        "freshness": fresh,
        "evidence": w["evidence_bonus"] if data.has_evidence else 0.0,
        "location": w["location_bonus"] if data.location_verified else 0.0,
        "confirmations": min(data.confirmations * w["confirmation_step"], w["confirmation_cap"]),
        "contradictions": -min(
            data.contradictions * w["contradiction_step"], w["contradiction_cap"]
        ),
        "reputation": (data.contributor_reputation - 0.5) * w["reputation_weight"],
    }
    raw = (
        base * fresh
        + factors["evidence"]
        + factors["location"]
        + factors["confirmations"]
        + factors["contradictions"]
        + factors["reputation"]
    )
    score = max(0.0, min(1.0, raw))
    if data.source == "USER" and not data.has_evidence:
        # Votes and device location are cheap to fake (throwaway accounts, spoofed GPS).
        # A consumer price needs evidence to be rated HIGH, whatever the votes say.
        ceiling = w["high_from"] - 0.001
        factors["no_evidence_ceiling"] = ceiling if score > ceiling else 0.0
        score = min(score, ceiling)
    return Confidence(
        score=Decimal(str(score)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        level=level_for(score, w),
        factors=factors,
    )


def input_field_names() -> set[str]:
    return {f.name for f in fields(ConfidenceInput)}
