from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.contributions.extraction import MAX_TEXT_CHARS, Origin, extract


def values(extraction):
    return [p.value for p in extraction.prices]


class TestPrices:
    def test_reads_a_price_with_currency(self):
        result = extract("ARROZ TIO JOAO 5KG\nR$ 24,90")
        assert values(result) == [Decimal("24.90")]
        assert result.prices[0].has_currency and result.prices[0].raw == "R$ 24,90"

    def test_reads_thousands_separator_and_dot_decimal(self):
        assert values(extract("R$ 1.249,90")) == [Decimal("1249.90")]
        assert values(extract("24.90")) == [Decimal("24.90")]

    def test_price_with_currency_comes_first(self):
        result = extract("de 29,90\npor R$ 24,90")
        assert values(result) == [Decimal("24.90"), Decimal("29.90")]

    def test_unit_price_and_quantity_are_not_shelf_prices(self):
        result = extract("R$ 24,90\nR$ 4,98/kg\n1,50 kg\n2,5 L")
        assert values(result) == [Decimal("24.90")]

    def test_ignores_numbers_that_are_not_prices(self):
        assert extract("Lote 12345\nValidade 12/2026\n500g").prices == []

    def test_zero_and_absurd_prices_are_dropped(self):
        assert extract("R$ 0,00").prices == []

    def test_same_price_twice_on_a_line_is_one_candidate(self):
        assert values(extract("R$ 9,99 R$ 9,99")) == [Decimal("9.99")]

    def test_everything_read_is_labelled_a_fact(self):
        result = extract("R$ 24,90\n7891000100103")
        assert {p.origin for p in result.prices} == {Origin.FACT}
        assert {g.origin for g in result.gtins} == {Origin.FACT}


class TestGtin:
    def test_valid_ean13_is_found_and_padded(self):
        result = extract("Arroz\n7891000100103")
        assert [g.gtin for g in result.gtins] == ["07891000100103"]

    def test_wrong_check_digit_is_not_a_gtin(self):
        assert extract("7891000100104").gtins == []

    def test_barcode_digits_are_not_read_as_a_price(self):
        assert extract("7891000100103").prices == []


class TestNameLines:
    def test_keeps_text_lines_without_the_price_and_code(self):
        result = extract("ARROZ BRANCO TIO JOAO 5KG R$ 24,90\n7891000100103\n---")
        assert result.name_lines == ["ARROZ BRANCO TIO JOAO 5KG"]

    def test_empty_text_yields_nothing(self):
        result = extract("")
        assert (result.prices, result.gtins, result.name_lines) == ([], [], [])


def test_text_too_long_is_refused():
    with pytest.raises(ValidationError):
        extract("a" * (MAX_TEXT_CHARS + 1))
