from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.promotions import engine as e
from apps.promotions.engine import PurchaseContext, calculate_line, validate_rule

FORTALEZA = ZoneInfo("America/Fortaleza")
D = Decimal


def at(day, hour, minute=0):
    """2026-10-07 is a Wednesday (weekday 2)."""
    return datetime(2026, 10, day, hour, minute, tzinfo=FORTALEZA)


CTX = PurchaseContext(at=at(7, 12))


def line(price, qty, rule, ctx=CTX):
    return calculate_line(price, qty, rule, ctx)


class TestFixedPriceBundle:
    RULE = {"type": "FIXED_PRICE", "bundle_quantity": 3, "bundle_price": "20.00"}

    def test_spec_example_three_for_twenty_with_five_units(self):
        result = line("10.00", 5, self.RULE)
        assert result.applicable
        assert (result.gross, result.net, result.savings) == (D("50.00"), D("40.00"), D("10.00"))

    @pytest.mark.parametrize(
        ("qty", "net"),
        [(1, "10.00"), (2, "20.00"), (3, "20.00"), (4, "30.00"), (6, "40.00"), (7, "50.00")],
    )
    def test_quantities_around_the_bundle(self, qty, net):
        result = line("10.00", qty, self.RULE)
        assert result.net == D(net)

    def test_below_bundle_size_is_not_applicable_and_says_why(self):
        result = line("10.00", 2, self.RULE)
        assert not result.applicable
        assert "Leve 3" in result.reason
        assert result.net == result.gross == D("20.00")

    def test_single_unit_promotional_price(self):
        result = line("10.00", 4, {"type": "FIXED_PRICE", "bundle_price": "8.50"})
        assert result.net == D("34.00")

    def test_never_worse_than_the_normal_price(self):
        result = line(
            "10.00", 3, {"type": "FIXED_PRICE", "bundle_quantity": 3, "bundle_price": "35.00"}
        )
        assert not result.applicable
        assert result.net == result.gross == D("30.00")


class TestPercentage:
    def test_basic(self):
        assert line("20.00", 2, {"type": "PERCENTAGE", "percent": "10"}).net == D("36.00")

    def test_rounded_once_on_the_line_total_not_per_unit(self):
        # 3 x 9.99 = 29.97; 10% off = 26.973 -> 26.97. Per-unit rounding would give 8.99*3 = 26.97
        # here, so also check a case where the two differ: 3 x 0.55 at 15% off.
        result = line("0.55", 3, {"type": "PERCENTAGE", "percent": "15"})
        assert result.net == D("1.40")  # 1.65 * 0.85 = 1.4025 -> 1.40 (per unit: 0.47 * 3 = 1.41)

    def test_half_cent_rounds_up(self):
        assert line("0.05", 1, {"type": "PERCENTAGE", "percent": "50"}).net == D("0.03")  # 0.025

    def test_full_discount_is_free_not_negative(self):
        assert line("5.00", 2, {"type": "PERCENTAGE", "percent": "100"}).net == D("0.00")

    @pytest.mark.parametrize("percent", ["0", "-5", "100.01", "abc", ""])
    def test_invalid_percent_is_refused(self, percent):
        with pytest.raises(e.InvalidRule):
            validate_rule({"type": "PERCENTAGE", "percent": percent})

    def test_fractional_quantity_for_weighed_goods(self):
        result = line("39.90", "0.750", {"type": "PERCENTAGE", "percent": "10"})
        assert result.gross == D("29.93")  # 29.925 -> 29.93
        assert result.net == D("26.93")  # 26.9325


class TestBuyXPayY:
    RULE = {"type": "BUY_X_PAY_Y", "buy": 3, "pay": 2}

    @pytest.mark.parametrize(
        ("qty", "net"),
        [(3, "20.00"), (4, "30.00"), (5, "40.00"), (6, "40.00"), (7, "50.00")],
    )
    def test_groups(self, qty, net):
        assert line("10.00", qty, self.RULE).net == D(net)

    def test_not_enough_units(self):
        result = line("10.00", 2, self.RULE)
        assert not result.applicable and "Leve 3" in result.reason

    @pytest.mark.parametrize(
        "rule", [{"buy": 3, "pay": 3}, {"buy": 3, "pay": 4}, {"buy": 1, "pay": 1}, {"buy": 3}]
    )
    def test_invalid_rules(self, rule):
        with pytest.raises(e.InvalidRule):
            validate_rule({"type": "BUY_X_PAY_Y", **rule})


class TestSecondUnit:
    RULE = {"type": "SECOND_UNIT_DISCOUNT", "percent": "50"}

    @pytest.mark.parametrize(
        ("qty", "net"), [(2, "15.00"), (3, "25.00"), (4, "30.00"), (5, "40.00")]
    )
    def test_pairs(self, qty, net):
        assert line("10.00", qty, self.RULE).net == D(net)

    def test_single_unit(self):
        assert not line("10.00", 1, self.RULE).applicable


class TestQuantityDiscount:
    def test_percent_from_minimum(self):
        rule = {"type": "QUANTITY_DISCOUNT", "min_quantity": 3, "percent": "10"}
        assert not line("10.00", 2, rule).applicable
        assert line("10.00", 3, rule).net == D("27.00")
        assert line("10.00", 10, rule).net == D("90.00")

    def test_fixed_unit_price_from_minimum(self):
        rule = {"type": "QUANTITY_DISCOUNT", "min_quantity": 6, "unit_price": "8.00"}
        assert line("10.00", 6, rule).net == D("48.00")

    def test_percent_and_price_together_are_ambiguous(self):
        with pytest.raises(e.InvalidRule):
            validate_rule(
                {"type": "QUANTITY_DISCOUNT", "min_quantity": 3, "percent": "5", "unit_price": "9"}
            )


class TestConditionalPrices:
    def test_pix_price_only_with_pix(self):
        rule = {"type": "PIX_PRICE", "percent": "5"}
        assert not line("100.00", 1, rule).applicable
        assert "Pix" in line("100.00", 1, rule).reason
        paying_pix = PurchaseContext(at=at(7, 12), payment_condition="PIX")
        assert line("100.00", 1, rule, paying_pix).net == D("95.00")

    def test_loyalty_price_only_for_members(self):
        rule = {"type": "LOYALTY_PRICE", "unit_price": "7.90"}
        assert not line("9.90", 2, rule).applicable
        member = PurchaseContext(at=at(7, 12), has_loyalty=True)
        assert line("9.90", 2, rule, member).net == D("15.80")

    def test_coupon_requires_the_code_case_insensitive(self):
        rule = {"type": "COUPON", "code": "ECONOMIZA10", "percent": "10"}
        assert not line("50.00", 1, rule).applicable
        wrong = PurchaseContext(at=at(7, 12), coupon_codes=frozenset({"OUTRO"}))
        assert not line("50.00", 1, rule, wrong).applicable
        right = PurchaseContext(at=at(7, 12), coupon_codes=frozenset({"economiza10"}))
        assert line("50.00", 1, rule, right).net == D("45.00")

    def test_coupon_fixed_amount_cannot_go_negative(self):
        rule = {"type": "COUPON", "code": "X", "amount": "100.00"}
        ctx = PurchaseContext(at=at(7, 12), coupon_codes=frozenset({"X"}))
        result = line("30.00", 1, rule, ctx)
        assert result.net == D("0.00")

    def test_coupon_minimum_quantity(self):
        rule = {"type": "COUPON", "code": "X", "percent": "10", "min_quantity": 3}
        ctx = PurchaseContext(at=at(7, 12), coupon_codes=frozenset({"X"}))
        assert not line("10.00", 2, rule, ctx).applicable
        assert line("10.00", 3, rule, ctx).applicable


class TestCashback:
    def test_cashback_is_not_a_discount(self):
        result = line("100.00", 1, {"type": "CASHBACK", "percent": "5"})
        assert result.applicable
        assert result.net == result.gross == D("100.00")  # you still pay full price
        assert result.savings == D("0.00")
        assert result.cashback == D("5.00")
        assert result.effective_cost == D("95.00")

    def test_amount_per_unit_with_cap(self):
        rule = {"type": "CASHBACK", "amount_per_unit": "2.00", "max_cashback": "5.00"}
        assert line("10.00", 2, rule).cashback == D("4.00")
        assert line("10.00", 10, rule).cashback == D("5.00")

    def test_percent_and_amount_together_are_refused(self):
        with pytest.raises(e.InvalidRule):
            validate_rule({"type": "CASHBACK", "percent": "5", "amount_per_unit": "1"})


class TestTemporalRules:
    BASE = {"type": "PERCENTAGE", "percent": "20"}

    def test_day_limited_uses_local_weekday(self):
        rule = {"type": "DAY_LIMITED", "weekdays": [2], "base": self.BASE}  # Wednesday
        assert line("10.00", 1, rule, PurchaseContext(at=at(7, 12))).net == D("8.00")
        assert not line("10.00", 1, rule, PurchaseContext(at=at(8, 12))).applicable  # Thursday

    def test_weekday_is_evaluated_in_fortaleza_time_not_utc(self):
        rule = {"type": "DAY_LIMITED", "weekdays": [2], "base": self.BASE}
        # 01:30 UTC on Thursday 8th is still 22:30 Wednesday 7th in Fortaleza (UTC-3).
        utc_moment = datetime(2026, 10, 8, 1, 30, tzinfo=UTC)
        assert line("10.00", 1, rule, PurchaseContext(at=utc_moment)).applicable

    def test_time_window(self):
        rule = {
            "type": "TIME_LIMITED",
            "start_time": "18:00",
            "end_time": "20:00",
            "base": self.BASE,
        }
        assert line("10.00", 1, rule, PurchaseContext(at=at(7, 19))).applicable
        assert line(
            "10.00", 1, rule, PurchaseContext(at=at(7, 18, 0))
        ).applicable  # start inclusive
        assert not line(
            "10.00", 1, rule, PurchaseContext(at=at(7, 20, 0))
        ).applicable  # end exclusive
        assert "horário" in line("10.00", 1, rule, PurchaseContext(at=at(7, 12))).reason

    def test_window_crossing_midnight(self):
        rule = {
            "type": "TIME_LIMITED",
            "start_time": "22:00",
            "end_time": "06:00",
            "base": self.BASE,
        }
        for hour, expected in [(23, True), (3, True), (6, False), (12, False), (22, True)]:
            assert line("10.00", 1, rule, PurchaseContext(at=at(7, hour))).applicable is expected

    def test_temporal_wraps_any_base_rule(self):
        rule = {
            "type": "DAY_LIMITED",
            "weekdays": [2],
            "base": {"type": "BUY_X_PAY_Y", "buy": 3, "pay": 2},
        }
        result = line("10.00", 3, rule)
        assert result.net == D("20.00")
        assert result.rule_type == "DAY_LIMITED"

    def test_naive_datetime_is_rejected(self):
        rule = {"type": "DAY_LIMITED", "weekdays": [2], "base": self.BASE}
        with pytest.raises(ValueError):
            line("10.00", 1, rule, PurchaseContext(at=datetime(2026, 10, 7, 12)))

    @pytest.mark.parametrize(
        "rule",
        [
            {"type": "DAY_LIMITED", "weekdays": [], "base": {"type": "PERCENTAGE", "percent": "5"}},
            {
                "type": "DAY_LIMITED",
                "weekdays": [7],
                "base": {"type": "PERCENTAGE", "percent": "5"},
            },
            {
                "type": "DAY_LIMITED",
                "weekdays": [True],
                "base": {"type": "PERCENTAGE", "percent": "5"},
            },
            {"type": "DAY_LIMITED", "weekdays": [1]},
            {
                "type": "TIME_LIMITED",
                "start_time": "10:00",
                "end_time": "10:00",
                "base": {"type": "PERCENTAGE", "percent": "5"},
            },
            {
                "type": "TIME_LIMITED",
                "start_time": "25:99",
                "end_time": "10:00",
                "base": {"type": "PERCENTAGE", "percent": "5"},
            },
            {
                "type": "DAY_LIMITED",
                "weekdays": [1],
                "base": {
                    "type": "DAY_LIMITED",
                    "weekdays": [1],
                    "base": {"type": "PERCENTAGE", "percent": "5"},
                },
            },
        ],
    )
    def test_invalid_temporal_rules(self, rule):
        with pytest.raises(e.InvalidRule):
            validate_rule(rule)


class TestBestPromotion:
    RULES = [
        {"type": "PERCENTAGE", "percent": "10"},
        {"type": "FIXED_PRICE", "bundle_quantity": 3, "bundle_price": "20.00"},
        {"type": "PIX_PRICE", "percent": "30"},  # needs Pix: not applicable here
    ]

    def test_picks_the_largest_benefit_without_stacking(self):
        best, results = e.best_promotion("10.00", 3, self.RULES, CTX)
        assert best.rule_type == "FIXED_PRICE" and best.net == D("20.00")  # beats 10% (27.00)
        assert len(results) == 3
        assert [r.applicable for r in results] == [True, True, False]

    def test_no_stacking_the_other_rules_do_not_add_up(self):
        best, _ = e.best_promotion("10.00", 3, self.RULES, CTX)
        assert best.savings == D("10.00")  # not 10 + 3

    def test_cashback_competes_on_total_benefit(self):
        rules = [{"type": "PERCENTAGE", "percent": "2"}, {"type": "CASHBACK", "percent": "10"}]
        best, _ = e.best_promotion("100.00", 1, rules, CTX)
        assert best.rule_type == "CASHBACK"

    def test_none_applicable(self):
        best, results = e.best_promotion("10.00", 1, [self.RULES[1]], CTX)
        assert best is None and not results[0].applicable

    def test_deterministic_tie_goes_to_the_earlier_rule(self):
        rules = [
            {"type": "PERCENTAGE", "percent": "10"},
            {"type": "COUPON", "code": "X", "percent": "10"},
        ]
        ctx = PurchaseContext(at=at(7, 12), coupon_codes=frozenset({"X"}))
        best, _ = e.best_promotion("10.00", 1, rules, ctx)
        assert best.rule_type == "PERCENTAGE"


class TestSafety:
    def test_floats_are_rejected_everywhere(self):
        with pytest.raises(TypeError):
            line(9.9, 1, {"type": "PERCENTAGE", "percent": "10"})
        with pytest.raises(TypeError):
            line("9.90", 1.5, {"type": "PERCENTAGE", "percent": "10"})
        with pytest.raises(e.InvalidRule):
            validate_rule({"type": "PERCENTAGE", "percent": 10.5})

    @pytest.mark.parametrize(("price", "qty"), [("0", 1), ("-1", 1), ("5", 0), ("5", -2)])
    def test_non_positive_values(self, price, qty):
        with pytest.raises(ValueError):
            line(price, qty, {"type": "PERCENTAGE", "percent": "10"})

    def test_unknown_type(self):
        with pytest.raises(e.InvalidRule):
            validate_rule({"type": "FREE_STUFF"})

    def test_every_spec_type_is_supported(self):
        spec = {
            "PERCENTAGE",
            "FIXED_PRICE",
            "BUY_X_PAY_Y",
            "SECOND_UNIT_DISCOUNT",
            "QUANTITY_DISCOUNT",
            "CASHBACK",
            "PIX_PRICE",
            "LOYALTY_PRICE",
            "COUPON",
            "TIME_LIMITED",
            "DAY_LIMITED",
        }
        assert set(e.ALL_TYPES) == spec

    def test_gross_is_always_the_normal_price_times_quantity(self):
        for rule in self.__class__.RULES_SAMPLE:
            result = line(
                "3.33",
                7,
                rule,
                PurchaseContext(at=at(7, 12), payment_condition="PIX", has_loyalty=True),
            )
            assert result.gross == D("23.31")
            assert result.net <= result.gross

    RULES_SAMPLE = [
        {"type": "PERCENTAGE", "percent": "33.3"},
        {"type": "FIXED_PRICE", "bundle_quantity": 2, "bundle_price": "5.00"},
        {"type": "BUY_X_PAY_Y", "buy": 3, "pay": 2},
        {"type": "SECOND_UNIT_DISCOUNT", "percent": "70"},
        {"type": "PIX_PRICE", "unit_price": "2.99"},
        {"type": "LOYALTY_PRICE", "percent": "12.5"},
    ]
