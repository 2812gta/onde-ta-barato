"""Engine tests on synthetic data. Expected numbers are computed by hand in the comments."""

from datetime import datetime
from decimal import Decimal
from itertools import permutations
from zoneinfo import ZoneInfo

import pytest

from apps.promotions.engine import PurchaseContext
from apps.recommendations import config
from apps.recommendations.engine import (
    INSUFFICIENT,
    NO_SAFE_ANSWER,
    RECOMMENDED,
    TIE,
    plan_options,
    recommend,
)
from apps.recommendations.types import (
    BasketItem,
    PlanParams,
    PriceQuote,
    PromoOffer,
    StoreCandidate,
)

D = Decimal
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=ZoneInfo("America/Fortaleza"))


def quote(price, *, low=None, confidence=0.7, age=2.0, fresh="CURRENT", conflict=False):
    return PriceQuote(
        unit_price=D(price),
        low_price=D(low or price),
        condition="NORMAL",
        source="MERCHANT",
        age_hours=age,
        freshness=fresh,
        confidence=confidence,
        conflict=conflict,
    )


def store(sid, distance_m, prices, promos=None, **quote_kw):
    return StoreCandidate(
        store_id=sid,
        name=f"Loja {sid}",
        distance_m=distance_m,
        quotes={k: quote(v, **quote_kw) for k, v in prices.items()},
        promos=promos or {},
    )


def params(mode=config.ECONOMIZAR_MAIS, cost_per_km="0.80", max_stores=2, distances=None, ctx=None):
    return PlanParams(
        mode=mode,
        cost_per_km=D(cost_per_km),
        detour_factor=D("1.3"),
        max_stores=max_stores,
        context=ctx or PurchaseContext(at=NOW),
        store_distances_m=distances or {},
    )


ITEMS = [BasketItem("arroz", D(1), "Arroz 5kg"), BasketItem("feijao", D(2), "Feijão 1kg")]


def pair_distances(**kw):
    return {frozenset(k.split("-")): v for k, v in kw.items()}


class TestCostAndTransport:
    # A at 1 km: 25 + 2x6.00 = 37.00; route 2 km x1.3 = 2.6 km x R$0.80 = 2.08 -> 39.08
    # B at 5 km: 24 + 2x5.50 = 35.00; route 10 km x1.3 = 13 km x R$0.80 = 10.40 -> 45.40
    A = {"arroz": "25.00", "feijao": "6.00"}
    B = {"arroz": "24.00", "feijao": "5.50"}

    def stores(self):
        return [store("A", 1000, self.A), store("B", 5000, self.B)]

    def test_totals_are_computed_exactly(self):
        plans = {p.store_ids: p for p in plan_options(ITEMS, self.stores(), params(max_stores=1))}
        a, b = plans[("A",)], plans[("B",)]
        assert (a.items_total, a.transport_cost, a.effective_total) == (
            D("37.00"),
            D("2.08"),
            D("39.08"),
        )
        assert (b.items_total, b.transport_cost, b.effective_total) == (
            D("35.00"),
            D("10.40"),
            D("45.40"),
        )
        assert a.route_km == pytest.approx(2.6)

    def test_transport_can_make_the_cheaper_basket_lose(self):
        result = recommend(ITEMS, self.stores(), params(max_stores=1))
        assert result.plans[0].store_ids == ("A",)  # B has cheaper items but is far away

    def test_without_travel_cost_the_cheaper_basket_wins(self):
        result = recommend(ITEMS, self.stores(), params(cost_per_km="0", max_stores=1))
        assert result.plans[0].store_ids == ("B",)
        assert result.plans[0].transport_cost == D("0.00")

    def test_nearest_mode_prefers_proximity_even_if_pricier(self):
        far_cheap = [
            store("A", 500, {"arroz": "30.00", "feijao": "8.00"}),
            store("B", 6000, self.B),
        ]
        result = recommend(
            ITEMS, far_cheap, params(mode=config.MAIS_PROXIMO, cost_per_km="0", max_stores=1)
        )
        assert result.plans[0].store_ids == ("A",)
        economise = recommend(ITEMS, far_cheap, params(cost_per_km="0", max_stores=1))
        assert economise.plans[0].store_ids == (
            "B",
        )  # same data, different intent, different answer


class TestSplitPurchases:
    # A (1.0 km): arroz 20 feijao 9 -> 29 + 2.08 = 31.08     B (1.2 km): arroz 28 feijao 4(x2=8) ...
    def stores(self):
        return [
            store("A", 1000, {"arroz": "20.00", "feijao": "9.00"}),
            store("B", 1200, {"arroz": "28.00", "feijao": "4.00"}),
        ]

    # pair: arroz at A (20.00) + 2 feijao at B (8.00) = 28.00; route 1000+500+1200 = 2700 m
    #       x1.3 = 3.51 km x 0.80 = 2.808 -> 2.81; effective 30.81 < single A (20+18+2.08 = 40.08)
    def test_split_wins_when_it_saves_more_than_the_extra_trip_costs(self):
        result = recommend(ITEMS, self.stores(), params(distances=pair_distances(**{"A-B": 500})))
        best = result.plans[0]
        assert set(best.store_ids) == {"A", "B"}
        assert (best.items_total, best.transport_cost, best.effective_total) == (
            D("28.00"),
            D("2.81"),
            D("30.81"),
        )
        assert {ln.item_key: ln.store_id for ln in best.lines} == {"arroz": "A", "feijao": "B"}

    def test_split_loses_when_travel_is_expensive(self):
        # R$ 20/km: single A = 38 + 2.6 km x 20 = 90.00; split = 28 + 3.51 km x 20 = 98.20
        result = recommend(
            ITEMS, self.stores(), params(cost_per_km="20", distances=pair_distances(**{"A-B": 500}))
        )
        assert result.plans[0].store_ids == ("A",)
        assert result.plans[0].effective_total == D("90.00")
        split = next(p for p in result.plans if len(p.store_ids) == 2)
        assert split.effective_total == D("98.20")

    def test_split_margin_is_decided_by_numbers_not_by_default(self):
        # R$ 10/km: single A = 38 + 26.00 = 64.00; split = 28 + 35.10 = 63.10 -> split still wins
        result = recommend(
            ITEMS, self.stores(), params(cost_per_km="10", distances=pair_distances(**{"A-B": 500}))
        )
        assert len(result.plans[0].store_ids) == 2
        assert result.plans[0].effective_total == D("63.10")

    def test_max_stores_one_disables_splitting(self):
        plans = plan_options(ITEMS, self.stores(), params(max_stores=1))
        assert all(len(p.store_ids) == 1 for p in plans)

    def test_least_travel_mode_never_splits(self):
        result = recommend(ITEMS, self.stores(), params(mode=config.MENOS_DESLOCAMENTO))
        assert all(len(p.store_ids) == 1 for p in result.plans)
        assert result.assumptions["max_stores"] == 1

    def test_unknown_distance_between_stores_is_assumed_worst_case(self):
        plans = plan_options(ITEMS, self.stores(), params())
        pair = next(p for p in plans if len(p.store_ids) == 2)
        # via the shopper: 1000 + (1000+1200) + 1200 = 4400 m x 1.3 = 5.72 km
        assert pair.route_km == pytest.approx(5.72)

    def test_a_split_never_uses_a_store_that_gets_no_items(self):
        stores = [
            store("A", 1000, {"arroz": "10.00", "feijao": "3.00"}),
            store("B", 1000, {"arroz": "99.00", "feijao": "99.00"}),
        ]
        assert all(len(p.store_ids) == 1 for p in plan_options(ITEMS, stores, params()))


class TestCoverageAndHonesty:
    def test_complete_plans_always_outrank_partial_ones(self):
        complete = store("A", 3000, {"arroz": "25.00", "feijao": "6.00"})
        partial_cheap = store("B", 500, {"arroz": "1.00"})  # super cheap, but has 50% of the list
        result = recommend(ITEMS, [complete, partial_cheap], params(max_stores=1))
        assert result.plans[0].store_ids == ("A",) and result.plans[0].complete
        assert not result.plans[-1].complete

    def test_partial_result_is_flagged(self):
        stores = [store("A", 1000, {"arroz": "25.00"}), store("B", 1200, {"arroz": "26.00"})]
        result = recommend(ITEMS, stores, params(max_stores=1))
        assert result.verdict == RECOMMENDED  # 50% coverage is the minimum
        assert result.plans[0].missing == ("feijao",)
        assert any("parcial" in w.lower() for w in result.warnings)
        assert any("50%" in r.text for r in result.reasons)

    def test_no_prices_at_all(self):
        result = recommend(ITEMS, [], params())
        assert (result.verdict, result.message, result.plans) == (INSUFFICIENT, NO_SAFE_ANSWER, ())

    def test_stores_without_any_price_for_the_list(self):
        result = recommend(ITEMS, [store("A", 1000, {"leite": "5.00"})], params())
        assert result.verdict == INSUFFICIENT and not result.plans

    def test_a_single_store_is_not_a_comparison(self):
        result = recommend(
            ITEMS, [store("A", 1000, {"arroz": "25.00", "feijao": "6.00"})], params()
        )
        assert result.verdict == INSUFFICIENT
        assert result.message == NO_SAFE_ANSWER
        assert any("menos de duas lojas" in w for w in result.warnings)
        assert result.plans  # the data we do have is still shown
        assert result.reasons == ()  # but no justification is invented

    def test_low_coverage_refuses_to_recommend(self):
        items = [BasketItem(k, D(1)) for k in ("a", "b", "c", "d")]
        stores = [store("A", 1000, {"a": "1.00"}), store("B", 1200, {"a": "1.10"})]
        result = recommend(items, stores, params())
        assert result.verdict == INSUFFICIENT
        assert any("menos da metade" in w for w in result.warnings)

    def test_low_confidence_refuses_to_recommend(self):
        stores = [
            store("A", 1000, {"arroz": "25.00", "feijao": "6.00"}, confidence=0.2),
            store("B", 1200, {"arroz": "24.00", "feijao": "6.50"}, confidence=0.2),
        ]
        result = recommend(ITEMS, stores, params())
        assert result.verdict == INSUFFICIENT
        assert any("confiança baixa" in w for w in result.warnings)

    def test_equal_options_are_a_tie_not_a_winner(self):
        prices = {"arroz": "25.00", "feijao": "6.00"}
        result = recommend(ITEMS, [store("A", 1000, prices), store("B", 1000, prices)], params())
        assert result.verdict == TIE
        assert "empatadas" in result.message

    def test_clear_winner_is_recommended(self):
        stores = [
            store("A", 1000, {"arroz": "20.00", "feijao": "5.00"}),
            store("B", 4000, {"arroz": "30.00", "feijao": "9.00"}),
        ]
        assert recommend(ITEMS, stores, params(max_stores=1)).verdict == RECOMMENDED

    def test_empty_basket_is_a_programming_error(self):
        with pytest.raises(ValueError):
            recommend([], [store("A", 1, {"x": "1"})], params())


class TestPromotions:
    THREE_FOR_20 = {"type": "FIXED_PRICE", "bundle_quantity": 3, "bundle_price": "20.00"}

    def basket(self):
        return [BasketItem("arroz", D(5), "Arroz")]

    def with_promo(self, confirmed):
        offer = PromoOffer("p1", "3 por R$ 20", self.THREE_FOR_20, confirmed)
        a = store("A", 1000, {"arroz": "10.00"}, promos={"arroz": (offer,)})
        b = store("B", 1000, {"arroz": "10.50"})
        return [a, b]

    def test_confirmed_promotion_is_applied_with_the_spec_example(self):
        # 5 x R$10: 3 for R$20 + 2 x R$10 = R$40 (gross R$50)
        plan = recommend(self.basket(), self.with_promo(True), params(cost_per_km="0")).plans[0]
        line = plan.lines[0]
        assert (line.gross, line.net, line.savings, line.promo_title) == (
            D("50.00"),
            D("40.00"),
            D("10.00"),
            "3 por R$ 20",
        )
        assert plan.promos_applied == 1 and plan.savings_total == D("10.00")

    def test_unconfirmed_promotion_does_not_count_but_is_disclosed(self):
        result = recommend(self.basket(), self.with_promo(False), params(cost_per_km="0"))
        plan = next(p for p in result.plans if p.store_ids == ("A",))
        assert plan.lines[0].net == D("50.00") and plan.promos_applied == 0
        assert plan.unconfirmed_potential_total == D("10.00")
        assert result.plans[0].store_ids == (
            "A",
        )  # best plan is the one carrying the unconfirmed promo
        assert any("não confirmada" in w and "R$ 10,00" in w for w in result.warnings)

    def test_unconfirmed_promotion_cannot_change_the_winner(self):
        # Without the promotion A costs 52.50 and B 50.00. A would win only if the UNCONFIRMED
        # promotion were trusted (A = 20 + 2 x 10.50 = 41.00 after it). It must not be.
        offer = PromoOffer("p1", "3 por R$ 20", self.THREE_FOR_20, False)
        a = store("A", 1000, {"arroz": "10.50"}, promos={"arroz": (offer,)})
        b = store("B", 1000, {"arroz": "10.00"})
        result = recommend(self.basket(), [a, b], params(cost_per_km="0"))
        assert result.plans[0].store_ids == ("B",)
        plan_a = next(p for p in result.plans if p.store_ids == ("A",))
        assert plan_a.effective_total == D("52.50")
        assert plan_a.unconfirmed_potential_total == D("11.50")  # 52.50 - 41.00
        # the same promotion, once confirmed, does flip the result
        confirmed = PromoOffer("p1", "3 por R$ 20", self.THREE_FOR_20, True)
        a2 = store("A", 1000, {"arroz": "10.50"}, promos={"arroz": (confirmed,)})
        flipped = recommend(self.basket(), [a2, b], params(cost_per_km="0"))
        assert flipped.plans[0].store_ids == ("A",)
        assert flipped.plans[0].effective_total == D("41.00")

    def test_promotion_that_does_not_apply_is_ignored(self):
        offer = PromoOffer("p2", "Só no Pix", {"type": "PIX_PRICE", "percent": "20"}, True)
        a = store("A", 1000, {"arroz": "10.00"}, promos={"arroz": (offer,)})
        plan = recommend(
            self.basket(), [a, store("B", 1000, {"arroz": "10.00"})], params(cost_per_km="0")
        ).plans[0]
        assert plan.promos_applied == 0
        paying_pix = PurchaseContext(at=NOW, payment_condition="PIX")
        pix_plan = recommend(
            self.basket(),
            [a, store("B", 1000, {"arroz": "10.00"})],
            params(cost_per_km="0", ctx=paying_pix),
        ).plans[0]
        assert pix_plan.lines[0].net == D("40.00")

    def test_cashback_lowers_effective_cost_but_not_the_price_paid(self):
        offer = PromoOffer("p3", "10% de volta", {"type": "CASHBACK", "percent": "10"}, True)
        a = store("A", 1000, {"arroz": "10.00"}, promos={"arroz": (offer,)})
        plan = next(
            p
            for p in recommend(
                self.basket(), [a, store("B", 1000, {"arroz": "10.50"})], params(cost_per_km="0")
            ).plans
            if p.store_ids == ("A",)
        )
        assert plan.items_total == D("50.00")  # you still pay the full price at the register
        assert plan.cashback_total == D("5.00")
        assert plan.effective_total == D("45.00")

    def test_promotions_mode_values_promotions_more(self):
        offer = PromoOffer("p4", "30% off", {"type": "PERCENTAGE", "percent": "30"}, True)
        promo_store = store("A", 3000, {"arroz": "10.50"}, promos={"arroz": (offer,)})
        plain_store = store("B", 500, {"arroz": "10.00"})
        items = [BasketItem("arroz", D(2))]
        near = recommend(
            items, [promo_store, plain_store], params(mode=config.MAIS_PROXIMO, cost_per_km="0")
        )
        promo = recommend(
            items,
            [promo_store, plain_store],
            params(mode=config.MELHORES_PROMOCOES, cost_per_km="0"),
        )
        assert near.plans[0].store_ids == ("B",)
        assert promo.plans[0].store_ids == ("A",)


class TestConflictsAndFreshness:
    def conflicted(self):
        a = StoreCandidate(
            "A",
            "Loja A",
            1000,
            {
                "arroz": quote("20.00", low="18.90", confidence=0.49, conflict=True),
                "feijao": quote("6.00"),
            },
        )
        return [a, store("B", 1100, {"arroz": "21.00", "feijao": "6.20"})]

    def test_conflicting_price_uses_the_higher_value_and_reports_the_optimistic_total(self):
        result = recommend(ITEMS, self.conflicted(), params(cost_per_km="0", max_stores=1))
        a = next(p for p in result.plans if p.store_ids == ("A",))
        assert a.items_total == D("32.00")  # 20.00 + 2 x 6.00 (not the 18.90)
        assert a.optimistic_total == D("30.90")  # 18.90 + 12.00 if the low price is the real one
        assert a.conflicts == 1
        assert any("conflitantes" in w and "R$ 30,90" in w for w in result.warnings)

    def test_conflict_lowers_the_confidence_of_the_plan(self):
        result = recommend(ITEMS, self.conflicted(), params(cost_per_km="0", max_stores=1))
        a = next(p for p in result.plans if p.store_ids == ("A",))
        b = next(p for p in result.plans if p.store_ids == ("B",))
        assert a.avg_confidence < b.avg_confidence

    def test_stale_prices_are_called_out(self):
        stores = [
            store("A", 1000, {"arroz": "20.00", "feijao": "5.00"}, fresh="STALE", age=300),
            store("B", 1200, {"arroz": "26.00", "feijao": "6.50"}),
        ]
        result = recommend(ITEMS, stores, params(max_stores=1))
        assert result.plans[0].store_ids == ("A",)
        assert any("2 preço(s) desatualizado(s)" in w for w in result.warnings)

    def test_freshness_ratio_counts_recent_prices(self):
        stores = [
            StoreCandidate(
                "A", "A", 1000, {"arroz": quote("25.00", age=2), "feijao": quote("6.00", age=100)}
            ),
            store("B", 1200, {"arroz": "26.00", "feijao": "6.50"}),
        ]
        plan = next(
            p for p in plan_options(ITEMS, stores, params(max_stores=1)) if p.store_ids == ("A",)
        )
        assert plan.fresh_ratio == pytest.approx(0.5)


class TestExplanations:
    def stores(self):
        return [
            store("A", 1000, {"arroz": "20.00", "feijao": "5.00"}),
            store("B", 4000, {"arroz": "30.00", "feijao": "9.00"}),
            store("C", 3000, {"arroz": "29.00", "feijao": "8.50"}),
        ]

    def test_reasons_are_built_from_the_real_numbers(self):
        result = recommend(ITEMS, self.stores(), params(max_stores=1))
        text = " | ".join(r.text for r in result.reasons)
        assert "100% da sua lista disponível" in text
        assert "mais barato que a média das outras opções" in text
        assert "km de você" in text
        assert "dos preços atualizados nas últimas 24 h" in text
        assert result.plans[0].store_ids == ("A",)

    def test_price_advantage_percentage_is_correct(self):
        # A: 30.00 + 2.08 = 32.08 ; B: 48 + 8.32*... compute from the plans instead of trusting text
        result = recommend(ITEMS, self.stores(), params(max_stores=1))
        best = result.plans[0]
        others = result.plans[1:]
        average = sum(p.effective_total for p in others) / len(others)
        expected = round(float((average - best.effective_total) / average) * 100)
        reason = next(r for r in result.reasons if r.code == "PRICE_VS_AVERAGE")
        assert f"{expected}% mais barato" in reason.text

    def test_when_the_winner_is_not_the_cheapest_the_explanation_says_so(self):
        stores = [
            store("A", 400, {"arroz": "30.00", "feijao": "8.00"}),
            store("B", 9000, {"arroz": "24.00", "feijao": "5.50"}),
        ]
        result = recommend(
            ITEMS, stores, params(mode=config.MAIS_PROXIMO, cost_per_km="0", max_stores=1)
        )
        assert result.plans[0].store_ids == ("A",)
        cheaper = next(r for r in result.reasons if r.code == "CHEAPER_ALTERNATIVE")
        assert "Loja B" in cheaper.text and "mais barata" in cheaper.text

    def test_split_explanation_mentions_two_stops(self):
        stores = [
            store("A", 1000, {"arroz": "20.00", "feijao": "9.00"}),
            store("B", 1200, {"arroz": "28.00", "feijao": "4.00"}),
        ]
        result = recommend(ITEMS, stores, params(distances=pair_distances(**{"A-B": 500})))
        assert any("2 paradas" in r.text for r in result.reasons)

    def test_every_assumption_is_disclosed(self):
        result = recommend(ITEMS, self.stores(), params(max_stores=1))
        for key in (
            "cost_per_km",
            "detour_factor",
            "distance_basis",
            "conflicting_prices",
            "promotions",
        ):
            assert key in result.assumptions
        assert any("Os preços podem divergir do caixa" in w for w in result.warnings)

    def test_money_is_formatted_in_brazilian_style(self):
        from apps.recommendations.explain import brl

        assert brl(D("1234.5")) == "R$ 1.234,50"
        assert brl(D("0.05")) == "R$ 0,05"


class TestScoringProperties:
    def test_components_and_score_are_bounded(self):
        stores = [
            store("A", 800, {"arroz": "25.00", "feijao": "6.00"}),
            store("B", 5000, {"arroz": "22.00", "feijao": "5.00"}),
        ]
        for mode in config.MODES:
            for plan in recommend(ITEMS, stores, params(mode=mode)).plans:
                assert 0 <= plan.score <= 1.0000001
                assert all(0 <= v <= 1.0000001 for v in plan.components.values())

    def test_weights_of_every_mode_sum_to_one(self):
        for mode in config.MODES:
            weights = config.weights_for(mode)
            assert set(weights) == set(config.COMPONENTS)
            assert sum(weights.values()) == pytest.approx(1.0)

    def test_no_commercial_component_exists(self):
        banned = ("sponsor", "advert", "subscription", "plan_", "budget", "commercial", "paid")
        for name in config.COMPONENTS:
            assert not any(word in name for word in banned)

    def test_result_is_independent_of_the_order_stores_are_given(self):
        stores = [
            store("A", 1000, {"arroz": "20.00", "feijao": "9.00"}),
            store("B", 1200, {"arroz": "28.00", "feijao": "4.00"}),
            store("C", 2500, {"arroz": "19.00", "feijao": "10.00"}),
        ]
        distances = pair_distances(**{"A-B": 500, "A-C": 1500, "B-C": 1200})
        reference = [
            (p.store_ids, p.effective_total)
            for p in recommend(ITEMS, stores, params(distances=distances)).plans
        ]
        for order in permutations(stores):
            result = recommend(ITEMS, list(order), params(distances=distances))
            assert [(p.store_ids, p.effective_total) for p in result.plans] == reference

    def test_item_order_does_not_change_the_choice(self):
        stores = [
            store("A", 1000, {"arroz": "20.00", "feijao": "9.00"}),
            store("B", 1200, {"arroz": "28.00", "feijao": "4.00"}),
        ]
        forward = recommend(ITEMS, stores, params()).plans[0]
        backward = recommend(list(reversed(ITEMS)), stores, params()).plans[0]
        assert (forward.store_ids, forward.effective_total) == (
            backward.store_ids,
            backward.effective_total,
        )

    def test_scores_are_not_compared_across_complete_and_partial_tiers(self):
        complete = store("A", 3000, {"arroz": "25.00", "feijao": "6.00"})
        partial = store("B", 500, {"arroz": "1.00"})
        result = recommend(ITEMS, [complete, partial], params(max_stores=1))
        tiers = [p.complete for p in result.plans]
        assert tiers == sorted(tiers, reverse=True)  # all complete first
