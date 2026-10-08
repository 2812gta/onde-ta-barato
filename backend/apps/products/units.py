"""Price per comparable unit. Embalagens diferentes nunca são comparadas pelo preço absoluto."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from apps.core.money import to_decimal

# base unit -> (display unit, how many base units per display unit)
_DISPLAY = {
    "g": ("kg", Decimal(1000)),
    "ml": ("l", Decimal(1000)),
    "un": ("un", Decimal(1)),
    "m": ("m", Decimal(1)),
}
_PRECISION = Decimal("0.0001")


class NotComparable(ValueError):
    """Units belong to different dimensions (e.g. weight vs volume)."""


@dataclass(frozen=True)
class UnitPrice:
    amount: Decimal  # price per `per`, 4 decimals (kept precise for comparison)
    per: str  # kg, l, un, m

    def display(self) -> str:
        """Human string, e.g. 'R$ 4,98/kg'. Rounds to cents for display only."""
        cents = self.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        text = f"{cents:.2f}".replace(".", ",")
        return f"R$ {text}/{self.per}"

    def is_cheaper_than(self, other: "UnitPrice") -> bool:
        if self.per != other.per:
            raise NotComparable(f"cannot compare price per {self.per} with price per {other.per}")
        return self.amount < other.amount


def unit_price(price: Decimal | str | int, base_amount: Decimal, base_unit: str) -> UnitPrice:
    if base_unit not in _DISPLAY:
        raise ValueError(f"unknown base unit: {base_unit}")
    if base_amount <= 0:
        raise ValueError("quantity must be positive")
    per, factor = _DISPLAY[base_unit]
    amount = to_decimal(price) / (base_amount / factor)
    return UnitPrice(amount=amount.quantize(_PRECISION, rounding=ROUND_HALF_UP), per=per)
