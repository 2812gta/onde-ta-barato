"""Fraud signals: deterministic rules that point a moderator at a contribution.

A signal never rejects, hides or re-scores a price on its own (CONTRIBUTION_POLICY.md):
one signal can be a coincidence. The rules are pure functions of a context so every
threshold is tested; gathering the context from the database lives in `services`.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import median
from typing import Any

from .models import FraudKind, FraudSeverity

OUTLIER_LOW_RATIO = Decimal("0.5")
OUTLIER_HIGH_RATIO = Decimal("2")
OUTLIER_MIN_SAMPLES = 3
BURST_LIMIT = 10  # confirmed contributions by one user inside BURST_WINDOW
BURST_WINDOW = timedelta(hours=1)
STALE_PHOTO_AFTER = timedelta(hours=6)


@dataclass(frozen=True)
class FraudContext:
    price: Decimal
    now: datetime
    captured_at: datetime | None
    recent_prices: list[Decimal]  # other prices of the same product, recent window
    photo_used_by_other_user: bool
    photo_used_by_same_user_elsewhere: bool
    recent_contributions_by_user: int
    near_store: bool | None  # None = the device did not send a location


@dataclass(frozen=True)
class Signal:
    kind: str
    severity: str
    detail: dict[str, Any]


def evaluate(ctx: FraudContext) -> list[Signal]:
    signals: list[Signal] = []

    if ctx.photo_used_by_other_user:
        signals.append(Signal(FraudKind.DUPLICATE_PHOTO, FraudSeverity.HIGH, {"by": "other_user"}))
    elif ctx.photo_used_by_same_user_elsewhere:
        signals.append(Signal(FraudKind.DUPLICATE_PHOTO, FraudSeverity.MEDIUM, {"by": "same_user"}))

    if len(ctx.recent_prices) >= OUTLIER_MIN_SAMPLES:
        typical = Decimal(str(median(ctx.recent_prices)))
        if typical > 0 and not (
            typical * OUTLIER_LOW_RATIO <= ctx.price <= typical * OUTLIER_HIGH_RATIO
        ):
            signals.append(
                Signal(
                    FraudKind.PRICE_OUTLIER,
                    FraudSeverity.MEDIUM,
                    {"price": str(ctx.price), "median": str(typical.quantize(Decimal("0.01")))},
                )
            )

    if ctx.recent_contributions_by_user >= BURST_LIMIT:
        signals.append(
            Signal(
                FraudKind.RATE_BURST,
                FraudSeverity.MEDIUM,
                {"count": ctx.recent_contributions_by_user, "window_minutes": 60},
            )
        )

    if ctx.near_store is None:
        signals.append(Signal(FraudKind.LOCATION_MISSING, FraudSeverity.LOW, {}))
    elif not ctx.near_store:
        signals.append(Signal(FraudKind.LOCATION_FAR, FraudSeverity.MEDIUM, {}))

    if ctx.captured_at is not None and ctx.now - ctx.captured_at > STALE_PHOTO_AFTER:
        age = int((ctx.now - ctx.captured_at).total_seconds() // 3600)
        signals.append(Signal(FraudKind.STALE_PHOTO, FraudSeverity.LOW, {"age_hours": age}))

    return signals
