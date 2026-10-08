"""Cost-benefit engine. Pure functions over the whitelisted types in `types.py`.

How it decides (all of it explainable, see docs/RECOMMENDATIONS.md):

1. Build candidate PLANS: buy everything at one store, or split between two stores.
2. Price each plan line with the quoted price, apply the best CONFIRMED promotion, and add the
   estimated cost of getting there (straight-line distance x detour x R$/km).
3. Score plans on five normalised components (cost, distance, coverage, promotions,
   confidence) with weights that depend on the shopper's chosen mode.
4. Complete plans (the whole list is available) always rank above partial ones.
5. Be honest: if the data cannot support a recommendation, say so instead of guessing.
"""

from collections.abc import Iterable, Sequence
from decimal import Decimal
from itertools import combinations

from apps.core.money import quantize_money
from apps.promotions.engine import best_promotion

from . import config
from .explain import build_reasons, build_warnings
from .types import (
    BasketItem,
    Plan,
    PlanLine,
    PlanParams,
    PriceQuote,
    Recommendation,
    StoreCandidate,
)

INSUFFICIENT = "INSUFFICIENT_DATA"
RECOMMENDED = "RECOMMENDED"
TIE = "TIE"
NO_SAFE_ANSWER = "Não foi possível determinar o melhor mercado com segurança."


# --- lines ------------------------------------------------------------------------------


def _price_line(
    item: BasketItem,
    store: StoreCandidate,
    quote: PriceQuote,
    unit_price: Decimal,
    params: PlanParams,
) -> tuple[Decimal, Decimal, Decimal, Decimal, str | None, Decimal]:
    """gross, net, savings, cashback, promo title, unconfirmed potential for one unit price."""
    gross = quantize_money(unit_price * item.quantity)
    offers = store.promos.get(item.key, ())
    confirmed = [o for o in offers if o.confirmed]
    unconfirmed = [o for o in offers if not o.confirmed]

    best, evaluated = best_promotion(
        unit_price, item.quantity, [o.rule for o in confirmed], params.context
    )
    potential_best, _ = best_promotion(
        unit_price, item.quantity, [o.rule for o in unconfirmed], params.context
    )
    potential = potential_best.benefit if potential_best else Decimal("0.00")
    if best is None:
        return gross, gross, Decimal("0.00"), Decimal("0.00"), None, potential
    title = confirmed[evaluated.index(best)].title
    return gross, best.net, best.savings, best.cashback, title, potential


def build_line(item: BasketItem, store: StoreCandidate, params: PlanParams) -> PlanLine | None:
    quote = store.quotes.get(item.key)
    if quote is None:
        return None
    gross, net, savings, cashback, title, potential = _price_line(
        item, store, quote, quote.unit_price, params
    )
    low_net = net
    if quote.conflict and quote.low_price != quote.unit_price:
        low_net = _price_line(item, store, quote, quote.low_price, params)[1]
    return PlanLine(
        item_key=item.key,
        label=item.label,
        store_id=store.store_id,
        quantity=item.quantity,
        unit_price=quote.unit_price,
        gross=gross,
        net=net,
        savings=savings,
        cashback=cashback,
        promo_title=title,
        unconfirmed_potential=potential,
        conflict=quote.conflict,
        low_net=low_net,
        confidence=quote.confidence,
        age_hours=quote.age_hours,
        freshness=quote.freshness,
        condition=quote.condition,
    )


# --- plans ------------------------------------------------------------------------------


def _route_m(stores: Sequence[StoreCandidate], params: PlanParams) -> float:
    if len(stores) == 1:
        return 2 * stores[0].distance_m
    a, b = stores
    between = params.store_distances_m.get(frozenset({a.store_id, b.store_id}))
    if between is None:  # unknown: assume the worst (go back through the shopper's location)
        between = a.distance_m + b.distance_m
    return a.distance_m + between + b.distance_m


def make_plan(
    items: Sequence[BasketItem],
    stores: Sequence[StoreCandidate],
    lines: Sequence[PlanLine],
    params: PlanParams,
) -> Plan:
    covered = {line.item_key for line in lines}
    missing = tuple(i.key for i in items if i.key not in covered)
    route_km = _route_m(stores, params) / 1000 * float(params.detour_factor)
    transport = quantize_money(Decimal(str(route_km)) * params.cost_per_km)
    items_total = sum((line.net for line in lines), Decimal("0.00"))
    cashback = sum((line.cashback for line in lines), Decimal("0.00"))
    gross = sum((line.gross for line in lines), Decimal("0.00"))
    gross_f = float(gross) or 1.0
    config_values = config.get()
    fresh_limit = config_values["fresh_hours"]
    return Plan(
        store_ids=tuple(s.store_id for s in stores),
        lines=tuple(lines),
        missing=missing,
        items_total=items_total,
        savings_total=sum((line.savings for line in lines), Decimal("0.00")),
        cashback_total=cashback,
        transport_cost=transport,
        effective_total=items_total - cashback + transport,
        optimistic_total=sum((line.low_net for line in lines), Decimal("0.00"))
        - cashback
        + transport,
        unconfirmed_potential_total=sum(
            (line.unconfirmed_potential for line in lines), Decimal("0.00")
        ),
        coverage=len(lines) / len(items),
        complete=not missing,
        route_km=route_km,
        avg_confidence=sum(float(line.gross) * line.confidence for line in lines) / gross_f,
        fresh_ratio=sum(1 for line in lines if line.age_hours <= fresh_limit) / len(lines),
        conflicts=sum(1 for line in lines if line.conflict),
        promos_applied=sum(1 for line in lines if line.promo_title),
        gross_total=gross,
    )


def _single_plans(
    items: Sequence[BasketItem], stores: Sequence[StoreCandidate], params: PlanParams
) -> list[Plan]:
    plans = []
    for store in stores:
        lines = [ln for ln in (build_line(i, store, params) for i in items) if ln is not None]
        if lines:
            plans.append(make_plan(items, [store], lines, params))
    return plans


def _pair_plans(
    items: Sequence[BasketItem], stores: Sequence[StoreCandidate], params: PlanParams
) -> list[Plan]:
    limit = config.get()["pair_candidates"]
    shortlist = sorted(stores, key=lambda s: (-len(s.quotes), s.distance_m, s.store_id))[:limit]
    plans = []
    for a, b in combinations(shortlist, 2):
        chosen: list[PlanLine] = []
        for item in items:
            options = [
                ln for ln in (build_line(item, a, params), build_line(item, b, params)) if ln
            ]
            if not options:
                continue
            # cheapest effective cost wins; ties go to the nearer store, then to the lower id
            distance = {a.store_id: a.distance_m, b.store_id: b.distance_m}
            chosen.append(
                min(
                    options,
                    key=lambda ln: (ln.net - ln.cashback, distance[ln.store_id], ln.store_id),
                )
            )
        used = {ln.store_id for ln in chosen}
        if len(used) < 2:  # one store ends up with nothing: that is just the single plan
            continue
        plans.append(make_plan(items, [s for s in (a, b) if s.store_id in used], chosen, params))
    return plans


def plan_options(
    items: Sequence[BasketItem], stores: Sequence[StoreCandidate], params: PlanParams
) -> list[Plan]:
    plans = _single_plans(items, stores, params)
    if params.max_stores >= 2 and len(stores) >= 2:
        plans += _pair_plans(items, stores, params)
    return plans


# --- scoring ----------------------------------------------------------------------------


def _inverse_normalised(values: Iterable[float]) -> list[float]:
    """1.0 for the smallest value, 0.0 for the largest; all 1.0 when they are equal."""
    values = list(values)
    low, high = min(values), max(values)
    if high == low:
        return [1.0] * len(values)
    return [(high - v) / (high - low) for v in values]


def score_plans(plans: Sequence[Plan], mode: str) -> list[Plan]:
    """Score complete and partial plans separately: a partial plan is cheap only because it
    leaves things out, so it must never be normalised against complete ones."""
    cfg = config.get()
    weights = config.weights_for(mode)
    scored: list[Plan] = []
    for tier in (True, False):
        group = [p for p in plans if p.complete is tier]
        if not group:
            continue
        cost = _inverse_normalised(float(p.effective_total) for p in group)
        distance = _inverse_normalised(p.route_km for p in group)
        for plan, c, d in zip(group, cost, distance, strict=True):
            share = float(plan.savings_total / plan.gross_total) if plan.gross_total else 0.0
            components = {
                "cost": c,
                "distance": d,
                "coverage": plan.coverage,
                "promotions": min(1.0, share / cfg["promo_full_score_share"]),
                "confidence": plan.avg_confidence,
            }
            score = sum(weights[name] * components[name] for name in config.COMPONENTS)
            scored.append(Plan(**{**plan.__dict__, "components": components, "score": score}))
    return scored


def rank(plans: Sequence[Plan]) -> list[Plan]:
    """Complete before partial, then score; ties broken by cost, distance and store ids so the
    order is deterministic."""
    return sorted(
        plans,
        key=lambda p: (not p.complete, -p.score, p.effective_total, p.route_km, p.store_ids),
    )


# --- verdict ----------------------------------------------------------------------------


def recommend(
    items: Sequence[BasketItem], stores: Sequence[StoreCandidate], params: PlanParams
) -> Recommendation:
    if not items:
        raise ValueError("the basket is empty")
    cfg = config.get()
    effective = params
    if params.mode == config.MENOS_DESLOCAMENTO and params.max_stores != 1:
        effective = PlanParams(**{**params.__dict__, "max_stores": 1})
    assumptions = {
        "mode": params.mode,
        "cost_per_km": str(params.cost_per_km),
        "detour_factor": str(params.detour_factor),
        "max_stores": effective.max_stores,
        "distance_basis": "linha reta até a loja x fator de desvio (estimativa)",
        "conflicting_prices": "o total usa o valor mais alto; o total otimista usa o mais baixo",
        "promotions": "somente promoções confirmadas (comerciante verificado) entram no total",
    }

    names = {s.store_id: s.name for s in stores}
    plans = plan_options(items, stores, effective)
    if not plans:
        return Recommendation(
            verdict=INSUFFICIENT,
            message=NO_SAFE_ANSWER,
            plans=(),
            reasons=(),
            warnings=("Nenhuma loja da região tem preço atual para os itens da lista.",),
            assumptions=assumptions,
        )

    ranked = rank(score_plans(plans, params.mode))
    best = ranked[0]
    singles = [p for p in ranked if len(p.store_ids) == 1]
    comparable_stores = sum(1 for p in singles if p.coverage >= cfg["min_coverage_for_comparison"])

    problems = []
    if best.coverage < cfg["min_coverage_for_comparison"]:
        problems.append("A melhor opção cobre menos da metade da sua lista.")
    if best.avg_confidence < cfg["min_confidence"]:
        problems.append(
            "Os preços encontrados têm confiança baixa (antigos, sem confirmação ou em conflito)."
        )
    if comparable_stores < 2:
        problems.append("Há menos de duas lojas com dados suficientes para comparar.")

    warnings = build_warnings(best, ranked, params)
    if problems:
        return Recommendation(
            verdict=INSUFFICIENT,
            message=NO_SAFE_ANSWER,
            plans=tuple(ranked),
            reasons=(),
            warnings=tuple(problems + warnings),
            assumptions=assumptions,
        )

    runner_up = ranked[1] if len(ranked) > 1 else None
    tied = (
        runner_up is not None
        and runner_up.complete == best.complete
        and best.score - runner_up.score < cfg["tie_margin"]
    )
    if tied:
        message = "As melhores opções estão praticamente empatadas; veja os detalhes de cada uma."
        verdict = TIE
    else:
        message = "Recomendado com base nos preços encontrados na nossa base."
        verdict = RECOMMENDED
    return Recommendation(
        verdict=verdict,
        message=message,
        plans=tuple(ranked),
        reasons=tuple(build_reasons(best, ranked, params, names)),
        warnings=tuple(warnings),
        assumptions=assumptions,
    )
