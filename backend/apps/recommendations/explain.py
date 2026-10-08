"""Human explanations (pt-BR) generated from the numbers of the chosen plan.

Rule: a sentence is only produced when the data behind it exists and supports it. Nothing is
hard-coded as a justification, and the same function states unfavourable facts too (e.g. when
the recommended option is not the cheapest).
"""

from collections.abc import Mapping, Sequence
from decimal import Decimal

from apps.core.money import quantize_money

from .types import Plan, PlanParams, Reason

SIGNIFICANT = 0.01  # differences below 1% are not worth a claim


def brl(value: Decimal) -> str:
    text = f"{quantize_money(value):,.2f}"
    return "R$ " + text.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(fraction: float) -> str:
    return f"{round(abs(fraction) * 100)}%"


def km(value: float) -> str:
    return f"{value:.1f}".replace(".", ",") + " km"


def label_for(plan: Plan, names: Mapping[str, str]) -> str:
    return " + ".join(names.get(sid, sid) for sid in plan.store_ids)


def build_reasons(
    best: Plan, ranked: Sequence[Plan], params: PlanParams, names: Mapping[str, str]
) -> list[Reason]:
    reasons: list[Reason] = []
    peers = [p for p in ranked if p is not best and p.complete == best.complete]

    # 1. List coverage
    if best.complete:
        reasons.append(Reason("COVERAGE", "100% da sua lista disponível", 1.0))
    else:
        reasons.append(
            Reason(
                "COVERAGE",
                f"{pct(best.coverage)} da sua lista disponível "
                f"({len(best.missing)} item(ns) sem preço nesta opção)",
                best.coverage,
            )
        )

    # 2. Price against the alternatives, stated honestly in both directions
    if peers:
        average = sum((p.effective_total for p in peers), Decimal(0)) / len(peers)
        if average > 0:
            diff = float((average - best.effective_total) / average)
            if diff >= SIGNIFICANT:
                reasons.append(
                    Reason(
                        "PRICE_VS_AVERAGE",
                        f"{pct(diff)} mais barato que a média das outras opções "
                        f"({brl(best.effective_total)} contra {brl(average)}, "
                        "deslocamento incluído)",
                        diff,
                    )
                )
            elif diff <= -SIGNIFICANT:
                reasons.append(
                    Reason(
                        "PRICE_VS_AVERAGE",
                        f"{pct(diff)} mais caro que a média das outras opções "
                        f"({brl(best.effective_total)} contra {brl(average)}); "
                        "outros critérios pesaram mais",
                        diff,
                    )
                )
            else:
                reasons.append(
                    Reason("PRICE_VS_AVERAGE", "Custo total semelhante ao das outras opções", diff)
                )
        cheapest = min(peers + [best], key=lambda p: p.effective_total)
        if cheapest is not best:
            gap = float((best.effective_total - cheapest.effective_total) / best.effective_total)
            if gap >= SIGNIFICANT:
                reasons.append(
                    Reason(
                        "CHEAPER_ALTERNATIVE",
                        f"A opção mais barata é {label_for(cheapest, names)} "
                        f"({brl(cheapest.effective_total)}, {pct(gap)} a menos), "
                        f"com {km(cheapest.route_km)} de deslocamento "
                        f"contra {km(best.route_km)} desta",
                        gap,
                    )
                )

    # 3. Distance
    if len(best.store_ids) == 1:
        reasons.append(
            Reason("DISTANCE", f"A {km(best.route_km / 2)} de você (estimativa)", best.route_km / 2)
        )
    else:
        reasons.append(
            Reason(
                "DISTANCE",
                f"Roteiro de {km(best.route_km)} em 2 paradas (estimativa)",
                best.route_km,
            )
        )

    # 4. Promotions (confirmed only)
    if best.promos_applied:
        reasons.append(
            Reason(
                "PROMOTIONS",
                f"{best.promos_applied} promoção(ões) confirmada(s) aplicável(is), "
                f"economia de {brl(best.savings_total)}",
                float(best.savings_total),
            )
        )

    # 5. Price freshness
    reasons.append(
        Reason(
            "FRESHNESS",
            f"{pct(best.fresh_ratio)} dos preços atualizados nas últimas 24 h",
            best.fresh_ratio,
        )
    )
    return reasons


def build_warnings(best: Plan, ranked: Sequence[Plan], params: PlanParams) -> list[str]:
    warnings: list[str] = []
    if not best.complete:
        warnings.append(
            f"Resultado parcial: {len(best.missing)} item(ns) da lista sem preço conhecido "
            "nas lojas da região."
        )
    if best.conflicts:
        warnings.append(
            f"{best.conflicts} preço(s) com informações conflitantes. "
            f"O total usa o valor mais alto ({brl(best.effective_total)}); "
            f"se o mais baixo for o correto, seria {brl(best.optimistic_total)}."
        )
    if best.unconfirmed_potential_total > 0:
        warnings.append(
            "Há promoção não confirmada (comerciante ainda sem verificação) que não foi contada; "
            f"possível economia de {brl(best.unconfirmed_potential_total)}."
        )
    stale = sum(1 for line in best.lines if line.freshness != "CURRENT")
    if stale:
        warnings.append(f"{stale} preço(s) desatualizado(s); confirme no local.")
    if params.cost_per_km > 0:
        warnings.append(
            f"Deslocamento estimado a {brl(params.cost_per_km)}/km sobre a distância em linha reta "
            f"(x{params.detour_factor} para as ruas)."
        )
    warnings.append("Os preços podem divergir do caixa.")
    return warnings
