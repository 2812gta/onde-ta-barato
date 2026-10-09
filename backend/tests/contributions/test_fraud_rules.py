from datetime import UTC, datetime, timedelta
from decimal import Decimal

from apps.contributions import fraud
from apps.contributions.models import FraudKind, FraudSeverity

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def ctx(**overrides):
    base = {
        "price": Decimal("24.90"),
        "now": NOW,
        "captured_at": NOW - timedelta(minutes=5),
        "recent_prices": [Decimal("24.00"), Decimal("25.00"), Decimal("26.00")],
        "photo_used_by_other_user": False,
        "photo_used_by_same_user_elsewhere": False,
        "recent_contributions_by_user": 0,
        "near_store": True,
    }
    return fraud.FraudContext(**{**base, **overrides})


def kinds(signals):
    return [s.kind for s in signals]


def test_a_normal_contribution_raises_no_signal():
    assert fraud.evaluate(ctx()) == []


class TestDuplicatePhoto:
    def test_photo_from_another_user_is_high(self):
        (signal,) = fraud.evaluate(ctx(photo_used_by_other_user=True))
        assert (signal.kind, signal.severity) == (FraudKind.DUPLICATE_PHOTO, FraudSeverity.HIGH)

    def test_own_photo_reused_is_medium(self):
        (signal,) = fraud.evaluate(ctx(photo_used_by_same_user_elsewhere=True))
        assert signal.severity == FraudSeverity.MEDIUM

    def test_other_user_wins_over_same_user(self):
        signals = fraud.evaluate(
            ctx(photo_used_by_other_user=True, photo_used_by_same_user_elsewhere=True)
        )
        assert len(signals) == 1 and signals[0].severity == FraudSeverity.HIGH


class TestPriceOutlier:
    def test_far_below_the_median(self):
        assert kinds(fraud.evaluate(ctx(price=Decimal("10.00")))) == [FraudKind.PRICE_OUTLIER]

    def test_far_above_the_median(self):
        assert kinds(fraud.evaluate(ctx(price=Decimal("60.00")))) == [FraudKind.PRICE_OUTLIER]

    def test_boundaries_are_inclusive(self):
        assert fraud.evaluate(ctx(price=Decimal("12.50"))) == []  # exactly half of 25
        assert fraud.evaluate(ctx(price=Decimal("50.00"))) == []  # exactly double

    def test_too_few_samples_to_judge(self):
        recent = [Decimal("25.00"), Decimal("25.00")]
        assert fraud.evaluate(ctx(price=Decimal("1.00"), recent_prices=recent)) == []


class TestBurst:
    def test_at_the_limit_raises_a_signal(self):
        signals = fraud.evaluate(ctx(recent_contributions_by_user=fraud.BURST_LIMIT))
        assert kinds(signals) == [FraudKind.RATE_BURST]

    def test_just_below_the_limit_does_not(self):
        assert fraud.evaluate(ctx(recent_contributions_by_user=fraud.BURST_LIMIT - 1)) == []


class TestLocation:
    def test_far_from_the_store(self):
        assert kinds(fraud.evaluate(ctx(near_store=False))) == [FraudKind.LOCATION_FAR]

    def test_location_not_sent_is_only_low(self):
        (signal,) = fraud.evaluate(ctx(near_store=None))
        assert (signal.kind, signal.severity) == (FraudKind.LOCATION_MISSING, FraudSeverity.LOW)


class TestStalePhoto:
    def test_old_photo(self):
        signals = fraud.evaluate(ctx(captured_at=NOW - timedelta(hours=7)))
        assert kinds(signals) == [FraudKind.STALE_PHOTO]
        assert signals[0].detail == {"age_hours": 7}

    def test_no_capture_time_is_not_judged(self):
        assert fraud.evaluate(ctx(captured_at=None)) == []


def test_signals_accumulate_instead_of_one_deciding():
    signals = fraud.evaluate(
        ctx(price=Decimal("1.00"), near_store=False, photo_used_by_other_user=True)
    )
    assert set(kinds(signals)) == {
        FraudKind.DUPLICATE_PHOTO,
        FraudKind.PRICE_OUTLIER,
        FraudKind.LOCATION_FAR,
    }
