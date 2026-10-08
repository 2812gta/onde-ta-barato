from decimal import Decimal

import pytest

from apps.core.money import quantize_money


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10", "10.00"),
        ("2.675", "2.68"),  # ROUND_HALF_UP, not banker's rounding
        ("2.665", "2.67"),
        ("0.004", "0.00"),
        ("0.005", "0.01"),
        (3, "3.00"),
        (Decimal("24.9") * 3, "74.70"),
    ],
)
def test_quantize_rounds_half_up(raw, expected):
    assert quantize_money(raw) == Decimal(expected)


def test_float_is_rejected():
    with pytest.raises(TypeError):
        quantize_money(24.9)  # type: ignore[arg-type]


def test_out_of_range_is_rejected():
    with pytest.raises(ValueError):
        quantize_money("99999999999.99")
