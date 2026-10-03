"""Tests for the Venezuelan number formatters (utils/formatters.py)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from opticamanager.utils.formatters import (
    _group_thousands,
    format_bs,
    format_usd,
    format_ve,
    format_ve_int,
)


class TestFormatVe:
    @pytest.mark.parametrize(
        ("value", "decimals", "expected"),
        [
            (1234567.89, 2, "1.234.567,89"),
            (42.5, 0, "42"),  # round() banker's rounding: round(42.5) == 42
            (0, 2, "0,00"),
            (-1234.5, 2, "-1.234,50"),
            (Decimal("1234.56"), 2, "1.234,56"),
            (999, 0, "999"),
            (1000, 0, "1.000"),
            (1.005, 2, "1,00"),  # repr(1.005) < 1.005 → "{:.2f}" == "1.00"
        ],
    )
    def test_format_ve(
        self, value: float | Decimal, decimals: int, expected: str
    ) -> None:
        assert format_ve(value, decimals) == expected


class TestFormatVeDecimal:
    """The Decimal path must skip float, which costs precision."""

    def test_no_pierde_precision_en_importes_grandes(self) -> None:
        # 12345678.91 as an exact Decimal; through float it would deform.
        assert format_ve(Decimal("12345678.91")) == "12.345.678,91"

    def test_no_pierde_precision_en_decimales_finos(self) -> None:
        assert format_ve(Decimal("0.07")) == "0,07"
        assert format_ve(Decimal("1.10")) == "1,10"

    def test_usa_bankers_rounding_en_decimal(self) -> None:
        assert format_ve(Decimal("42.5"), 0) == "42"
        assert format_ve(Decimal("43.5"), 0) == "44"

    def test_acepta_un_solo_decimal(self) -> None:
        assert format_ve(Decimal("7.5"), 1) == "7,5"

    def test_negocio_con_signo(self) -> None:
        assert format_ve(Decimal("-1234.56")) == "-1.234,56"
        assert format_ve(Decimal("-42.5"), 0) == "-42"


class TestGroupThousands:
    @pytest.mark.parametrize(
        ("integer_part", "expected"),
        [
            ("0", "0"),
            ("1", "1"),
            ("999", "999"),
            ("1000", "1.000"),
            ("1234567", "1.234.567"),
        ],
    )
    def test_group_thousands(self, integer_part: str, expected: str) -> None:
        assert _group_thousands(integer_part) == expected


class TestFormatHelpers:
    def test_format_ve_int(self) -> None:
        assert format_ve_int(12345) == "12.345"
        assert format_ve_int(Decimal("12345")) == "12.345"

    def test_format_bs(self) -> None:
        assert format_bs(1234.56) == "Bs. 1.234,56"

    def test_format_usd(self) -> None:
        assert format_usd(1234.56) == "$ 1.234,56"
