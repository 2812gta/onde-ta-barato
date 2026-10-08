from decimal import Decimal

import pytest

from apps.products.normalization import parse_quantity
from apps.products.units import NotComparable, unit_price


def per_unit(price, text):
    q = parse_quantity(text)
    return unit_price(price, q.base_amount, q.base_unit)


def test_rice_example_from_the_spec():
    a = per_unit("24.90", "5kg")
    b = per_unit("5.50", "1kg")
    assert a.display() == "R$ 4,98/kg"
    assert b.display() == "R$ 5,50/kg"
    assert a.is_cheaper_than(b)  # the 5 kg bag is cheaper per kg despite the higher sticker price
    assert not b.is_cheaper_than(a)


def test_absolute_price_would_have_misled():
    assert Decimal("24.90") > Decimal("5.50")  # naive comparison says the opposite


def test_grams_are_reported_per_kg():
    assert per_unit("3.00", "500g").display() == "R$ 6,00/kg"


def test_volume_per_liter():
    assert per_unit("7.50", "1,5l").display() == "R$ 5,00/l"
    assert per_unit("2.10", "350ml").display() == "R$ 6,00/l"


def test_multipack_uses_total_volume():
    assert per_unit("42.00", "12x350ml").display() == "R$ 10,00/l"


def test_units_and_meters():
    assert per_unit("12.00", "12 un").display() == "R$ 1,00/un"
    assert per_unit("9.00", "3 m").display() == "R$ 3,00/m"


def test_weight_and_volume_are_not_comparable():
    with pytest.raises(NotComparable):
        per_unit("5.00", "1kg").is_cheaper_than(per_unit("5.00", "1l"))


def test_precision_is_kept_for_comparison_and_rounded_only_for_display():
    price = per_unit("10.00", "3kg")
    assert price.amount == Decimal("3.3333")
    assert price.display() == "R$ 3,33/kg"


@pytest.mark.parametrize("base_amount", [Decimal(0), Decimal(-1)])
def test_invalid_quantity(base_amount):
    with pytest.raises(ValueError):
        unit_price("1.00", base_amount, "g")


def test_unknown_base_unit():
    with pytest.raises(ValueError):
        unit_price("1.00", Decimal(1), "lb")
