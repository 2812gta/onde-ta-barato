"""Identifier validators. Check digits are verified, not just the format."""

import re

from django.core.exceptions import ValidationError

_NON_DIGITS = re.compile(r"\D")


def digits_only(value: str) -> str:
    return _NON_DIGITS.sub("", value or "")


def _cnpj_digit(base: str, weights: list[int]) -> str:
    total = sum(int(d) * w for d, w in zip(base, weights, strict=True))
    remainder = total % 11
    return "0" if remainder < 2 else str(11 - remainder)


def normalize_cnpj(value: str) -> str:
    """Return the 14-digit CNPJ or raise ValidationError (format, repeated digits, check digits)."""
    cnpj = digits_only(value)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        raise ValidationError("CNPJ inválido.")
    first = _cnpj_digit(cnpj[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = _cnpj_digit(cnpj[:12] + first, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    if cnpj[12:] != first + second:
        raise ValidationError("CNPJ inválido.")
    return cnpj


def normalize_gtin(value: str) -> str:
    """Validate GTIN-8/12/13/14 (GS1 mod-10) and return it left-padded to 14 digits.

    Padding makes the same product identical whether it was read as EAN-13 or GTIN-14.
    """
    gtin = digits_only(value)
    if len(gtin) not in (8, 12, 13, 14):
        raise ValidationError("GTIN/EAN inválido.")
    body, check = gtin[:-1], int(gtin[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    if (10 - total % 10) % 10 != check:
        raise ValidationError("GTIN/EAN inválido (dígito verificador).")
    return gtin.zfill(14)
