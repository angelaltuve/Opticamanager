"""Venezuelan standard number formatting.

Thousands separator: ``.``
Decimal separator: ``,``

Example: ``1.234.567,89``
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal


def _a_decimal_exacto(value: float | Decimal, decimals: int) -> Decimal:
    """Quantize to *decimals* places using banker's rounding.

    Only ``Decimal`` input reaches this. It skips the ``Decimal -> float ->
    Decimal`` round trip that costs precision on amounts, while keeping the
    rounding mode the ``float`` path already uses.
    """
    exp = Decimal(1).scaleb(-decimals)
    return Decimal(value).quantize(exp, rounding=ROUND_HALF_EVEN)


def format_ve(value: float | Decimal, decimals: int = 2) -> str:
    """Format a number using Venezuelan conventions.

    >>> format_ve(1234567.89)
    '1.234.567,89'
    >>> format_ve(Decimal("42.5"), 0)
    '42'

    Note: rounding follows Python rules, so round() uses *banker's rounding*
    (42.5 -> 42, not 43). ``Decimal`` input also goes through ROUND_HALF_EVEN
    so formatting an amount does not cost precision.
    """
    sign = "-" if value < 0 else ""

    if isinstance(value, Decimal):
        # Exact path: no intermediate float.
        rounded = _a_decimal_exacto(abs(value), decimals)
        formatted = f"{rounded:f}"
        if decimals == 0:
            return f"{sign}{_group_thousands(formatted)}"
        integer_part, _, decimal_part = formatted.partition(".")
        return f"{sign}{_group_thousands(integer_part)},{decimal_part}"

    if decimals == 0:
        rounded = round(abs(value))
        return f"{sign}{_group_thousands(str(rounded))}"

    fmt = f"{{:.{decimals}f}}"
    formatted = fmt.format(abs(value))
    integer_part, decimal_part = formatted.split(".")
    grouped = _group_thousands(integer_part)
    return f"{sign}{grouped},{decimal_part}"


def _group_thousands(integer_part: str) -> str:
    """Insert dots as thousands separators into an integer string."""
    grouped = ""
    for i, digit in enumerate(reversed(integer_part)):
        if i and i % 3 == 0:
            grouped = "." + grouped
        grouped = digit + grouped
    return grouped


def format_ve_int(value: float | int | Decimal) -> str:
    """Format an integer with Venezuelan thousands separator.

    >>> format_ve_int(12345)
    '12.345'
    """
    return format_ve(value, decimals=0)


def format_bs(value: float | Decimal, decimals: int = 2) -> str:
    """Format a value as Venezuelan Bolívares.

    >>> format_bs(1234.56)
    'Bs. 1.234,56'
    """
    return f"Bs. {format_ve(value, decimals)}"


def format_usd(value: float | Decimal, decimals: int = 2) -> str:
    """Format a value as US Dollars.

    >>> format_usd(1234.56)
    '$ 1.234,56'
    """
    return f"$ {format_ve(value, decimals)}"
