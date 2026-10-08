import pytest
from django.core.exceptions import ValidationError

from apps.core.validators import normalize_cnpj, normalize_gtin


class TestCnpj:
    @pytest.mark.parametrize(
        "raw", ["11.222.333/0001-81", "11222333000181", " 11 222 333 0001 81 "]
    )
    def test_valid_formats_normalize_to_digits(self, raw):
        assert normalize_cnpj(raw) == "11222333000181"

    @pytest.mark.parametrize(
        "raw", ["11222333000180", "00000000000000", "11111111111111", "123", "", "abcdefghijklmn"]
    )
    def test_invalid_values_are_rejected(self, raw):
        with pytest.raises(ValidationError):
            normalize_cnpj(raw)


class TestGtin:
    def test_ean13_is_padded_to_14_digits(self):
        assert normalize_gtin("7891000100103") == "07891000100103"

    def test_same_product_as_gtin14_is_identical(self):
        assert normalize_gtin("07891000100103") == normalize_gtin("7891000100103")

    @pytest.mark.parametrize("raw", ["40170725", "036000291452", "12345678901231"])
    def test_other_lengths_are_accepted_when_check_digit_is_valid(self, raw):
        assert len(normalize_gtin(raw)) == 14

    @pytest.mark.parametrize("raw", ["7891000100104", "789", "", "abc", "123456789012345"])
    def test_invalid_values_are_rejected(self, raw):
        with pytest.raises(ValidationError):
            normalize_gtin(raw)
