"""JSON shape of recommendation and comparison results. Money is always a string."""

from typing import Any

from .services import BasketResult, Comparison
from .types import Plan, PlanLine, Reason


def _line(line: PlanLine, names: dict[str, str]) -> dict[str, Any]:
    return {
        "variant_id": line.item_key,
        "label": line.label,
        "store_id": line.store_id,
        "store": names.get(line.store_id, ""),
        "quantity": str(line.quantity),
        "unit_price": str(line.unit_price),
        "gross": str(line.gross),
        "net": str(line.net),
        "savings": str(line.savings),
        "cashback": str(line.cashback),
        "promotion": line.promo_title,
        "unconfirmed_promotion_potential": str(line.unconfirmed_potential),
        "price_conflict": line.conflict,
        "price_condition": line.condition,
        "price_freshness": line.freshness,
        "price_age_hours": round(line.age_hours, 1),
        "price_confidence": round(line.confidence, 3),
    }


def plan(plan_: Plan, result: BasketResult) -> dict[str, Any]:
    return {
        "stores": [
            {
                "id": sid,
                "name": result.names.get(sid, ""),
                "distance_m": round(result.distances_m.get(sid, 0)),
            }
            for sid in plan_.store_ids
        ],
        "complete": plan_.complete,
        "coverage": round(plan_.coverage, 3),
        "missing_items": [
            {"variant_id": key, "label": result.labels.get(key, "")} for key in plan_.missing
        ],
        "items_total": str(plan_.items_total),
        "savings_total": str(plan_.savings_total),
        "cashback_total": str(plan_.cashback_total),
        "transport_cost": str(plan_.transport_cost),
        "effective_total": str(plan_.effective_total),
        "optimistic_total": str(plan_.optimistic_total),
        "unconfirmed_promotion_potential": str(plan_.unconfirmed_potential_total),
        "route_km": round(plan_.route_km, 2),
        "price_confidence": round(plan_.avg_confidence, 3),
        "fresh_price_share": round(plan_.fresh_ratio, 3),
        "conflicting_prices": plan_.conflicts,
        "promotions_applied": plan_.promos_applied,
        "score": round(plan_.score, 4),
        "score_breakdown": {k: round(v, 4) for k, v in plan_.components.items()},
        "lines": [_line(line, result.names) for line in plan_.lines],
    }


def reasons(items: tuple[Reason, ...]) -> list[dict[str, Any]]:
    return [{"code": r.code, "text": r.text, "value": r.value} for r in items]


def basket(result: BasketResult, *, mode: str) -> dict[str, Any]:
    rec = result.recommendation
    ranked = [plan(p, result) for p in rec.plans]
    recommended = rec.verdict in ("RECOMMENDED", "TIE")
    return {
        "generated_at": result.generated_at,
        "mode": mode,
        "verdict": rec.verdict,
        "message": rec.message,
        "best": ranked[0] if recommended and ranked else None,
        "alternatives": ranked[1:6] if recommended else ranked[:5],
        "reasons": reasons(rec.reasons),
        "warnings": list(rec.warnings),
        "assumptions": rec.assumptions,
        "searched": {
            "stores_in_radius": result.stores_in_radius,
            "stores_with_prices": result.stores_with_prices,
        },
    }


def comparison(result: Comparison) -> dict[str, Any]:
    variant = result.variant
    return {
        "variant_id": str(variant.pk),
        "label": result.label,
        "notes": result.notes,
        "analysis": result.analysis,
        "results": [
            {
                "rank": row.rank,
                "store": {
                    "id": str(row.store.pk),
                    "name": row.store.name,
                    "distance_m": round(row.store.distance.m),  # type: ignore[attr-defined]
                    "merchant_verified": bool(
                        row.store.merchant and row.store.merchant.is_verified
                    ),
                },
                "price": str(row.quote.unit_price),
                "price_range": (
                    [str(row.price_range[0]), str(row.price_range[1])] if row.price_range else None
                ),
                "price_conflict": row.quote.conflict,
                "payment_condition": row.quote.condition,
                "unit_price": {
                    "amount": str(row.unit_price.amount),
                    "per": row.unit_price.per,
                    "display": row.unit_price.display(),
                },
                "freshness": row.quote.freshness,
                "age_hours": round(row.quote.age_hours, 1),
                "confidence": round(row.quote.confidence, 3),
            }
            for row in result.rows
        ],
    }
