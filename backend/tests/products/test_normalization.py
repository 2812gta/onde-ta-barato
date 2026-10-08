from decimal import Decimal

import pytest

from apps.products.normalization import normalize_text, parse_product_text, parse_quantity


class TestNormalizeText:
    def test_accents_case_and_punctuation(self):
        assert normalize_text("ARROZ  Tio-João!") == "arroz tio joao"

    def test_decimal_separator_is_kept(self):
        assert normalize_text("Leite 1,5L") == "leite 1,5l"

    def test_empty(self):
        assert normalize_text("") == ""
        assert normalize_text(None) == ""  # type: ignore[arg-type]


class TestParseQuantity:
    @pytest.mark.parametrize(
        ("text", "amount", "unit"),
        [
            ("ARROZ 5KG", "5", "kg"),
            ("arroz 5 kg", "5", "kg"),
            ("Leite 1,5L", "1.5", "l"),
            ("leite 1.5 lt", "1.5", "l"),
            ("Feijão 500 gr", "500", "g"),
            ("Refri 350ML", "350", "ml"),
            ("Ovos 12 un", "12", "un"),
            ("Fita 3 m", "3", "m"),
        ],
    )
    def test_common_labels(self, text, amount, unit):
        parsed = parse_quantity(text)
        assert (parsed.amount, parsed.unit) == (Decimal(amount), unit)

    def test_multipack_is_multiplied(self):
        parsed = parse_quantity("Cerveja 12x350ml")
        assert parsed.amount == Decimal(4200)
        assert parsed.unit == "ml"
        assert parsed.pack_count == 12

    def test_base_units(self):
        kg = parse_quantity("5kg")
        assert (kg.base_amount, kg.base_unit) == (Decimal(5000), "g")
        liters = parse_quantity("1,5l")
        assert (liters.base_amount, liters.base_unit) == (Decimal(1500), "ml")

    @pytest.mark.parametrize("text", ["sem quantidade", "", "R$ 24,90", "0 kg"])
    def test_no_quantity(self, text):
        assert parse_quantity(text) is None

    def test_price_is_not_mistaken_for_quantity(self):
        assert parse_quantity("ARROZ R$ 24,90") is None


class TestParseProductText:
    BRANDS = ["Tio João", "Camil", "Tio"]

    def test_splits_name_brand_quantity(self):
        parsed = parse_product_text("ARROZ TIO JOÃO 5KG", self.BRANDS)
        assert parsed.name == "arroz"
        assert parsed.brand == "tio joao"
        assert (parsed.quantity.amount, parsed.quantity.unit) == (Decimal(5), "kg")

    def test_longest_brand_wins(self):
        assert parse_product_text("Arroz Tio João 1kg", self.BRANDS).brand == "tio joao"

    def test_unknown_brand_is_not_guessed(self):
        parsed = parse_product_text("ARROZ DESCONHECIDO 5KG", self.BRANDS)
        assert parsed.brand is None
        assert parsed.name == "arroz desconhecido"

    def test_spelling_variants_give_same_result(self):
        a = parse_product_text("ARROZ TIO JOÃO 5KG", self.BRANDS)
        b = parse_product_text("Arroz Tio Joao 5 kg", self.BRANDS)
        assert (a.name, a.brand, a.quantity) == (b.name, b.brand, b.quantity)

    def test_abbreviation_is_expanded(self):
        assert parse_product_text("Arroz tp 1 5kg", []).name == "arroz tipo 1"
