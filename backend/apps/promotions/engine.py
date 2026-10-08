"""Promotion engine: pure, deterministic, no database, no AI.

A rule is a plain dict (stored as JSON), e.g.::

    {"type": "FIXED_PRICE", "bundle_quantity": 3, "bundle_price": "20.00"}   # "3 por R$ 20"
    {"type": "BUY_X_PAY_Y", "buy": 3, "pay": 2}                              # leve 3, pague 2
    {"type": "DAY_LIMITED", "weekdays": [1], "base": {"type": "PERCENTAGE", "percent": "10"}}

Rules of the game (also documented in docs/PROMOTIONS.md):

* Money is Decimal. Everything is computed exactly and rounded ONCE, to the cent, on the
  line total (ROUND_HALF_UP). Never per unit.
* A promotion can only lower the price. If it would not, it is reported as not applicable.
* Conditions (payment, loyalty, coupon, weekday, time window) are checked explicitly and the
  reason a promotion was NOT applied is returned, so the app can say why.
* Cashback is not a discount: it is returned separately and never mixed into `net`.
* Only ONE promotion applies per line (no stacking), the one with the largest total benefit.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings

from apps.core.money import quantize_money

HUNDRED = Decimal(100)

# Promotion types (spec section 21/26)
PERCENTAGE = "PERCENTAGE"
FIXED_PRICE = "FIXED_PRICE"
BUY_X_PAY_Y = "BUY_X_PAY_Y"
SECOND_UNIT_DISCOUNT = "SECOND_UNIT_DISCOUNT"
QUANTITY_DISCOUNT = "QUANTITY_DISCOUNT"
CASHBACK = "CASHBACK"
PIX_PRICE = "PIX_PRICE"
LOYALTY_PRICE = "LOYALTY_PRICE"
COUPON = "COUPON"
TIME_LIMITED = "TIME_LIMITED"
DAY_LIMITED = "DAY_LIMITED"

BASE_TYPES = (
    PERCENTAGE,
    FIXED_PRICE,
    BUY_X_PAY_Y,
    SECOND_UNIT_DISCOUNT,
    QUANTITY_DISCOUNT,
    CASHBACK,
    PIX_PRICE,
    LOYALTY_PRICE,
    COUPON,
)
TEMPORAL_TYPES = (TIME_LIMITED, DAY_LIMITED)
ALL_TYPES = BASE_TYPES + TEMPORAL_TYPES


class InvalidRule(ValueError):
    """The rule is malformed. Raised when a merchant tries to save it, never at checkout."""


@dataclass(frozen=True)
class PurchaseContext:
    """What we know about the shopper's situation when the promotion is evaluated."""

    at: datetime
    payment_condition: str = "NORMAL"
    has_loyalty: bool = False
    coupon_codes: frozenset[str] = frozenset()


@dataclass(frozen=True)
class LineResult:
    rule_type: str
    applicable: bool
    quantity: Decimal
    unit_price: Decimal
    gross: Decimal  # unit_price * quantity, to the cent
    net: Decimal  # what the shopper pays for the line
    savings: Decimal  # gross - net
    cashback: Decimal = Decimal("0.00")  # money back later, NOT deducted from net
    reason: str = ""  # why it was not applied (empty when applicable)
    steps: tuple[str, ...] = field(default_factory=tuple)  # human-readable breakdown

    @property
    def benefit(self) -> Decimal:
        """Savings plus cashback: what the shopper effectively gains."""
        return self.savings + self.cashback

    @property
    def effective_cost(self) -> Decimal:
        return self.net - self.cashback


# --- parsing helpers -------------------------------------------------------------------


def _opt_dec(rule: Mapping[str, Any], key: str) -> Decimal | None:
    if key not in rule or rule[key] in (None, ""):
        return None
    value = rule[key]
    if isinstance(value, float):
        raise InvalidRule(f"'{key}' não pode ser float; use texto ou inteiro (ex.: \"9.90\").")
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise InvalidRule(f"'{key}' não é um número válido.") from exc


def _dec(rule: Mapping[str, Any], key: str) -> Decimal:
    value = _opt_dec(rule, key)
    if value is None:
        raise InvalidRule(f"'{key}' é obrigatório.")
    return value


def _int(rule: Mapping[str, Any], key: str, *, minimum: int) -> int:
    value = _dec(rule, key)
    if value != value.to_integral_value() or value < minimum:
        raise InvalidRule(f"'{key}' deve ser um inteiro >= {minimum}.")
    return int(value)


def _opt_int(rule: Mapping[str, Any], key: str, *, minimum: int) -> int | None:
    return None if _opt_dec(rule, key) is None else _int(rule, key, minimum=minimum)


def _percent(rule: Mapping[str, Any], key: str = "percent") -> Decimal:
    value = _dec(rule, key)
    if not 0 < value <= HUNDRED:
        raise InvalidRule(f"'{key}' deve estar entre 0 (exclusivo) e 100.")
    return value


def _money(rule: Mapping[str, Any], key: str) -> Decimal:
    value = _dec(rule, key)
    if value <= 0:
        raise InvalidRule(f"'{key}' deve ser positivo.")
    return value


def _percent_or_price(rule: Mapping[str, Any]) -> tuple[Decimal | None, Decimal | None]:
    has_percent, has_price = "percent" in rule, "unit_price" in rule
    if has_percent == has_price:
        raise InvalidRule("Informe exatamente um entre 'percent' e 'unit_price'.")
    return (_percent(rule), None) if has_percent else (None, _money(rule, "unit_price"))


def _clock(rule: Mapping[str, Any], key: str) -> time:
    try:
        hour, minute = str(rule[key]).split(":")
        return time(int(hour), int(minute))
    except (KeyError, ValueError) as exc:
        raise InvalidRule(f"'{key}' deve estar no formato HH:MM.") from exc


def validate_rule(rule: Mapping[str, Any], *, _nested: bool = False) -> None:
    """Raise InvalidRule if the rule cannot be calculated. Called when a promotion is saved."""
    kind = rule.get("type")
    if kind not in ALL_TYPES:
        raise InvalidRule(f"Tipo de promoção desconhecido: {kind!r}.")
    if kind in TEMPORAL_TYPES:
        if _nested:
            raise InvalidRule("Promoções temporais não podem ser aninhadas.")
        base = rule.get("base")
        if not isinstance(base, Mapping) or base.get("type") not in BASE_TYPES:
            raise InvalidRule("'base' deve ser uma regra não temporal válida.")
        validate_rule(base, _nested=True)
        if kind == TIME_LIMITED:
            if _clock(rule, "start_time") == _clock(rule, "end_time"):
                raise InvalidRule("Horário inicial e final não podem ser iguais.")
        else:
            days = rule.get("weekdays")
            if (
                not isinstance(days, list)
                or not days
                or any(
                    not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 6 for d in days
                )
            ):
                raise InvalidRule("'weekdays' deve listar dias de 0 (segunda) a 6 (domingo).")
        return
    if kind == PERCENTAGE:
        _percent(rule)
    elif kind == FIXED_PRICE:
        _opt_int(rule, "bundle_quantity", minimum=1)
        _money(rule, "bundle_price")
    elif kind == BUY_X_PAY_Y:
        if _int(rule, "pay", minimum=1) >= _int(rule, "buy", minimum=2):
            raise InvalidRule("'pay' deve ser menor que 'buy'.")
    elif kind == SECOND_UNIT_DISCOUNT:
        _percent(rule)
    elif kind in (QUANTITY_DISCOUNT, PIX_PRICE, LOYALTY_PRICE):
        _percent_or_price(rule)
        if kind == QUANTITY_DISCOUNT:
            _int(rule, "min_quantity", minimum=2)
    elif kind == CASHBACK:
        has_percent, has_amount = "percent" in rule, "amount_per_unit" in rule
        if has_percent == has_amount:
            raise InvalidRule("Informe exatamente um entre 'percent' e 'amount_per_unit'.")
        _percent(rule) if has_percent else _money(rule, "amount_per_unit")
        if "max_cashback" in rule:
            _money(rule, "max_cashback")
    elif kind == COUPON:
        if not str(rule.get("code", "")).strip():
            raise InvalidRule("'code' é obrigatório.")
        has_percent, has_amount = "percent" in rule, "amount" in rule
        if has_percent == has_amount:
            raise InvalidRule("Informe exatamente um entre 'percent' e 'amount'.")
        _percent(rule) if has_percent else _money(rule, "amount")
        _opt_int(rule, "min_quantity", minimum=1)


# --- calculation -----------------------------------------------------------------------


def _local(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("PurchaseContext.at must be timezone-aware")
    return moment.astimezone(ZoneInfo(settings.TIME_ZONE))


def _in_window(now: time, start: time, end: time) -> bool:
    if start < end:
        return start <= now < end
    return now >= start or now < end  # window crossing midnight, e.g. 22:00-06:00


def _result(
    kind: str,
    unit_price: Decimal,
    quantity: Decimal,
    raw_net: Decimal,
    steps: list[str],
    cashback: Decimal = Decimal(0),
) -> LineResult:
    gross = quantize_money(unit_price * quantity)
    net = quantize_money(raw_net)
    cash = quantize_money(cashback)
    if net >= gross and cash == 0:
        return not_applicable(kind, unit_price, quantity, "A promoção não reduz o preço.")
    return LineResult(
        rule_type=kind,
        applicable=True,
        quantity=quantity,
        unit_price=unit_price,
        gross=gross,
        net=min(net, gross),
        savings=gross - min(net, gross),
        cashback=cash,
        steps=tuple(steps),
    )


def not_applicable(kind: str, unit_price: Decimal, quantity: Decimal, reason: str) -> LineResult:
    gross = quantize_money(unit_price * quantity)
    return LineResult(
        rule_type=kind,
        applicable=False,
        quantity=quantity,
        unit_price=unit_price,
        gross=gross,
        net=gross,
        savings=Decimal("0.00"),
        reason=reason,
    )


def _pct(percent: Decimal) -> Decimal:
    return percent / HUNDRED


def _calculate_base(
    unit_price: Decimal, qty: Decimal, rule: Mapping[str, Any], ctx: PurchaseContext
) -> LineResult:
    kind = rule["type"]
    gross_exact = unit_price * qty

    if kind == PERCENTAGE:
        pct = _percent(rule)
        return _result(
            kind, unit_price, qty, gross_exact * (1 - _pct(pct)), [f"{pct}% de desconto"]
        )

    if kind == FIXED_PRICE:
        size = Decimal(_opt_int(rule, "bundle_quantity", minimum=1) or 1)
        bundle_price = _money(rule, "bundle_price")
        bundles = qty // size
        if bundles < 1:
            return not_applicable(kind, unit_price, qty, f"Leve {size} para ativar a promoção.")
        rest = qty - bundles * size
        raw = bundles * bundle_price + rest * unit_price
        steps = [f"{bundles} x pacote de {size} por R$ {bundle_price}"]
        if rest:
            steps.append(f"{rest} x preço normal R$ {unit_price}")
        return _result(kind, unit_price, qty, raw, steps)

    if kind == BUY_X_PAY_Y:
        buy, pay = Decimal(_int(rule, "buy", minimum=2)), Decimal(_int(rule, "pay", minimum=1))
        groups = qty // buy
        if groups < 1:
            return not_applicable(kind, unit_price, qty, f"Leve {buy} para ativar a promoção.")
        payable = groups * pay + (qty - groups * buy)
        return _result(
            kind,
            unit_price,
            qty,
            payable * unit_price,
            [f"Leve {buy}, pague {pay}: {groups} grupo(s)", f"Paga {payable} de {qty} unidade(s)"],
        )

    if kind == SECOND_UNIT_DISCOUNT:
        pct = _percent(rule)
        pairs = qty // 2
        if pairs < 1:
            return not_applicable(kind, unit_price, qty, "Leve 2 para ativar a promoção.")
        raw = gross_exact - pairs * unit_price * _pct(pct)
        return _result(
            kind, unit_price, qty, raw, [f"{pairs} segunda(s) unidade(s) com {pct}% off"]
        )

    if kind in (QUANTITY_DISCOUNT, PIX_PRICE, LOYALTY_PRICE):
        percent, fixed = _percent_or_price(rule)
        if kind == QUANTITY_DISCOUNT:
            minimum = Decimal(_int(rule, "min_quantity", minimum=2))
            if qty < minimum:
                return not_applicable(kind, unit_price, qty, f"Leve {minimum} ou mais.")
        elif kind == PIX_PRICE and ctx.payment_condition != "PIX":
            return not_applicable(kind, unit_price, qty, "Válido apenas para pagamento via Pix.")
        elif kind == LOYALTY_PRICE and not ctx.has_loyalty:
            return not_applicable(kind, unit_price, qty, "Exige participar do clube de fidelidade.")
        if percent is not None:
            return _result(
                kind, unit_price, qty, gross_exact * (1 - _pct(percent)), [f"{percent}% off"]
            )
        if fixed is None:  # pragma: no cover - validate_rule guarantees one of the two
            raise InvalidRule("Regra sem 'percent' nem 'unit_price'.")
        return _result(
            kind, unit_price, qty, fixed * qty, [f"Preço promocional R$ {fixed} por unidade"]
        )

    if kind == COUPON:
        code = str(rule["code"]).strip().upper()
        if code not in {c.strip().upper() for c in ctx.coupon_codes}:
            return not_applicable(kind, unit_price, qty, "Cupom não informado.")
        coupon_min = _opt_int(rule, "min_quantity", minimum=1)
        if coupon_min and qty < coupon_min:
            return not_applicable(
                kind, unit_price, qty, f"Cupom exige {coupon_min} ou mais unidades."
            )
        if "percent" in rule:
            pct = _percent(rule)
            return _result(
                kind, unit_price, qty, gross_exact * (1 - _pct(pct)), [f"Cupom {code}: {pct}% off"]
            )
        amount = _money(rule, "amount")
        return _result(
            kind,
            unit_price,
            qty,
            max(gross_exact - amount, Decimal(0)),
            [f"Cupom {code}: R$ {amount} off"],
        )

    if kind == CASHBACK:
        if "percent" in rule:
            cash = gross_exact * _pct(_percent(rule))
            note = f"{_percent(rule)}% de volta"
        else:
            cash = _money(rule, "amount_per_unit") * qty
            note = f"R$ {_money(rule, 'amount_per_unit')} de volta por unidade"
        if "max_cashback" in rule:
            cash = min(cash, _money(rule, "max_cashback"))
        return _result(
            kind,
            unit_price,
            qty,
            gross_exact,
            [note, "Cashback é devolvido depois da compra"],
            cash,
        )

    raise InvalidRule(f"Tipo de promoção desconhecido: {kind!r}.")  # pragma: no cover


def calculate_line(
    unit_price: Decimal | str,
    quantity: Decimal | int | str,
    rule: Mapping[str, Any],
    ctx: PurchaseContext,
) -> LineResult:
    """Apply one rule to one line. Never raises for a shopper-side mismatch, only for bad rules."""
    price = Decimal(str(unit_price)) if not isinstance(unit_price, Decimal) else unit_price
    qty = Decimal(str(quantity)) if not isinstance(quantity, Decimal) else quantity
    if isinstance(unit_price, float) or isinstance(quantity, float):
        raise TypeError("float is not allowed for prices or quantities")
    if price <= 0 or qty <= 0:
        raise ValueError("unit_price and quantity must be positive")
    validate_rule(rule)
    kind = rule["type"]
    if kind not in TEMPORAL_TYPES:
        return _calculate_base(price, qty, rule, ctx)

    local = _local(ctx.at)
    if kind == DAY_LIMITED and local.weekday() not in rule["weekdays"]:
        return not_applicable(kind, price, qty, "Fora dos dias da promoção.")
    if kind == TIME_LIMITED and not _in_window(
        local.time(), _clock(rule, "start_time"), _clock(rule, "end_time")
    ):
        return not_applicable(kind, price, qty, "Fora do horário da promoção.")
    inner = _calculate_base(price, qty, rule["base"], ctx)
    return LineResult(**{**inner.__dict__, "rule_type": kind})


def best_promotion(
    unit_price: Decimal | str,
    quantity: Decimal | int | str,
    rules: Iterable[Mapping[str, Any]],
    ctx: PurchaseContext,
) -> tuple[LineResult | None, list[LineResult]]:
    """The single best applicable rule (largest savings + cashback) and every evaluation.

    Ties go to the lowest net, then to the earlier rule, so the result is deterministic.
    """
    results = [calculate_line(unit_price, quantity, rule, ctx) for rule in rules]
    applicable = [(i, r) for i, r in enumerate(results) if r.applicable]
    if not applicable:
        return None, results
    _, best = min(applicable, key=lambda pair: (-pair[1].benefit, pair[1].net, pair[0]))
    return best, results
