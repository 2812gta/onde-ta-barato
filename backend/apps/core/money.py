"""Money helpers. Floats are rejected on purpose: they must never carry currency values."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("9999999999.99")  # fits NUMERIC(12,2)


def to_decimal(value: Decimal | int | str) -> Decimal:
    if isinstance(value, float):
        raise TypeError("float is not allowed for monetary values; use Decimal or str")
    return value if isinstance(value, Decimal) else Decimal(value)


def quantize_money(value: Decimal | int | str) -> Decimal:
    """Round to cents with ROUND_HALF_UP (Brazilian commercial convention)."""
    amount = to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
    if abs(amount) > MAX_AMOUNT:
        raise ValueError("amount out of range")
    return amount
