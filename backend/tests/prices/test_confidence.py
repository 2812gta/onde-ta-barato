import inspect

import pytest
from django.test import override_settings

from apps.prices import confidence
from apps.prices.confidence import (
    ConfidenceInput,
    compute_confidence,
    freshness_factor,
    input_field_names,
)

TTL = 240.0


def score(source="USER", **kwargs):
    kwargs.setdefault("age_hours", 0)
    kwargs.setdefault("ttl_hours", TTL)
    return compute_confidence(ConfidenceInput(source=source, **kwargs))


class TestSourceOrdering:
    def test_verified_merchant_is_most_reliable_direct_source(self):
        verified = score("MERCHANT", merchant_verified=True).score
        unverified = score("MERCHANT").score
        user = score("USER").score
        calculated = score("CALCULATED").score
        assert verified > unverified > user > calculated

    def test_verification_only_matters_for_merchant_source(self):
        assert score("USER", merchant_verified=True).score == score("USER").score

    def test_every_source_has_a_base_score(self):
        from apps.prices.models import PriceSource

        for source in PriceSource.values:
            assert 0 < score(source).score < 1


class TestFreshness:
    @pytest.mark.parametrize(
        ("ratio", "expected"),
        [(0, 1.0), (0.5, 1.0), (1.0, 0.6), (2.0, 0.2), (5.0, 0.1)],
    )
    def test_curve_anchor_points(self, ratio, expected):
        assert freshness_factor(ratio * TTL, TTL) == pytest.approx(expected)

    def test_monotonically_non_increasing(self):
        values = [freshness_factor(h, TTL) for h in range(0, 1200, 10)]
        assert all(a >= b for a, b in zip(values, values[1:], strict=False))

    def test_older_price_is_less_trustworthy(self):
        assert (
            score(age_hours=0).score > score(age_hours=TTL).score > score(age_hours=3 * TTL).score
        )

    def test_zero_ttl_does_not_crash(self):
        assert freshness_factor(10, 0) == 0.1


class TestVotes:
    def test_confirmations_help_but_are_capped(self):
        base = score().score
        assert score(confirmations=1).score > base
        assert score(confirmations=3).score == score(confirmations=100).score

    def test_contradictions_hurt_but_are_capped(self):
        base = score().score
        assert score(contradictions=1).score < base
        assert score(contradictions=3).score == score(contradictions=100).score

    def test_votes_plus_spoofable_location_still_cannot_reach_high_without_evidence(self):
        """Regression: 3 votes + location used to score 0.69 (HIGH) with no proof at all."""
        result = score("USER", confirmations=100, location_verified=True)
        assert result.level == "MEDIUM"
        assert result.score < 0.65
        assert "no_evidence_ceiling" in result.factors

    def test_the_ceiling_only_applies_to_unevidenced_consumer_prices(self):
        assert (
            score("USER", confirmations=3, location_verified=True, has_evidence=True).level
            == "HIGH"
        )
        assert score("MERCHANT", merchant_verified=True).level == "HIGH"
        assert score("FLYER", confirmations=1).level == "HIGH"

    def test_a_hundred_votes_alone_never_reach_high(self):
        """Fake confirmations from throwaway accounts must not buy a HIGH rating."""
        result = score("USER", confirmations=100)
        assert result.level != "HIGH"
        assert result.score < 0.65

    def test_evidence_can_lift_a_well_confirmed_price(self):
        assert score("USER", confirmations=3, has_evidence=True).level == "HIGH"

    def test_disputes_can_outweigh_confirmations(self):
        assert score(confirmations=1, contradictions=3).score < score(confirmations=1).score


class TestBonusesAndBounds:
    def test_location_and_evidence_bonuses(self):
        base = score().score
        assert score(has_evidence=True).score > base
        assert score(location_verified=True).score > base

    def test_neutral_reputation_has_no_effect_and_extremes_move_it(self):
        base = score().score
        assert score(contributor_reputation=0.5).score == base
        assert score(contributor_reputation=1.0).score > base
        assert score(contributor_reputation=0.0).score < base

    def test_score_is_always_within_unit_interval(self):
        best = score(
            "MERCHANT",
            merchant_verified=True,
            has_evidence=True,
            location_verified=True,
            confirmations=99,
            contributor_reputation=1.0,
        )
        worst = score("CALCULATED", age_hours=9999, contradictions=99, contributor_reputation=0.0)
        assert 0 <= worst.score <= best.score <= 1

    @pytest.mark.parametrize(
        ("value", "level"),
        [(0.0, "LOW"), (0.349, "LOW"), (0.35, "MEDIUM"), (0.649, "MEDIUM"), (0.65, "HIGH")],
    )
    def test_level_thresholds(self, value, level):
        assert confidence.level_for(value) == level


class TestExplainability:
    def test_every_factor_is_reported(self):
        factors = score("USER", confirmations=2, has_evidence=True).factors
        assert set(factors) == {
            "base",
            "freshness",
            "evidence",
            "location",
            "confirmations",
            "contradictions",
            "reputation",
        }  # no ceiling key: evidence was provided
        assert (
            factors["evidence"] > 0
            and factors["confirmations"] > 0
            and factors["contradictions"] == 0
        )

    def test_weights_are_configurable(self):
        with override_settings(PRICE_CONFIDENCE={"evidence_bonus": 0.3}):
            gain = float(score(has_evidence=True).score - score().score)
            assert gain == pytest.approx(0.3, abs=0.001)
        gain = float(score(has_evidence=True).score - score().score)
        assert gain == pytest.approx(0.1, abs=0.001)


class TestCommercialIsolation:
    """Payment must never buy trust. Verification is an editorial process, not a purchase."""

    FORBIDDEN = (
        "subscription",
        "plan",
        "sponsor",
        "advert",
        "campaign",
        "commercial",
        "budget",
        "paid",
        "premium",
    )

    def test_inputs_exclude_commercial_fields(self):
        for name in input_field_names():
            assert not any(word in name.lower() for word in self.FORBIDDEN), name

    def test_module_has_no_commercial_vocabulary(self):
        source = inspect.getsource(confidence).lower()
        # The docstring states the rule itself, so look at code lines only.
        code = "\n".join(
            line for line in source.splitlines() if not line.strip().startswith(("#", '"', "'"))
        )
        for word in ("subscription", "sponsor", "advertis", "commercial_score", "paid"):
            assert word not in code.replace('"""', ""), word
