"""Report export to Excel (.xlsx) with openpyxl."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from opticamanager.core.logging_config import get_logger

log = get_logger(__name__)

# ── Formatting constants ──────────────────────────────────────

HEADER_FILL = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
TITLE_FONT = Font(size=14, bold=True)
SUBTITLE_FONT = Font(size=10, italic=True, color="666666")
THIN_BORDER = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)

# Keywords that hint at column types (lowercase, no accents)
CURRENCY_HINTS = [
    "bs.",
    "total",
    "iva",
    "subtotal",
    "ticket",
    "prom.",
    "monto",
    "precio",
    "costo",
    "ganancia",
    "importe",
]
INTEGER_HINTS = [
    "ventas",
    "cant.",
    "veces",
    "stock",
    "count",
    "qty",
    "existencia",
    "minimo",
]


# ── Public API ────────────────────────────────────────────────


def export_report_to_excel(
    filepath: str | Path,
    headers: list[str],
    data: list[list[str]],
    title: str = "",
    subtitle: str = "",
) -> None:
    """Export tabular report data to a formatted Excel workbook.

    Args:
        filepath: Destination ``.xlsx`` path.
        headers: Column header labels.
        data: Rows of string data (already formatted for display).
        title: Optional report title printed at the top.
        subtitle: Optional period / summary line.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title[:31] if title else "Reporte"

    ncols = len(headers)
    header_row = _write_header_block(ws, headers, title, subtitle)

    # ── Body ──
    for row_idx, row_data in enumerate(data, start=header_row + 1):
        for col_idx, raw in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx)
            _write_cell_value(cell, raw, headers[col_idx - 1])
            cell.border = THIN_BORDER

    # ── Auto-width ──
    for col_idx in range(1, ncols + 1):
        max_len = len(str(headers[col_idx - 1]))
        for row_idx in range(header_row, header_row + len(data) + 1):
            val = ws.cell(row=row_idx, column=col_idx).value
            if val is not None:
                # Estimate display width accounting for number formats
                display = str(val)
                max_len = max(max_len, len(display))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 45)

    # ── Freeze below header ──
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)  # type: ignore[assignment]

    wb.save(filepath)
    log.info(
        "Excel exportado: %s — %d columnas × %d filas",
        filepath,
        ncols,
        len(data),
    )


# ── Internal helpers ──────────────────────────────────────────


def _write_header_block(
    ws: Any,
    headers: list[str],
    title: str,
    subtitle: str,
) -> int:
    """Write title / subtitle / header row. Returns the header row number."""
    row = 1

    if title:
        ws.merge_cells(
            start_row=row,
            start_column=1,
            end_row=row,
            end_column=len(headers),
        )
        cell = ws.cell(row=row, column=1, value=title)
        cell.font = TITLE_FONT
        row += 1

    if subtitle:
        ws.merge_cells(
            start_row=row,
            start_column=1,
            end_row=row,
            end_column=len(headers),
        )
        cell = ws.cell(row=row, column=1, value=subtitle)
        cell.font = SUBTITLE_FONT
        row += 1

    # Blank row before headers if we have title/subtitle
    if title or subtitle:
        row += 1

    header_row = row
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")
        cell.border = THIN_BORDER

    return header_row


def _to_number(raw: str) -> float | None:
    """Best-effort parse of a display string into a ``float``.

    Handles the Venezuelan decimal format (comma as decimal separator,
    period as thousands separator):

    - ``"1.234,56"`` → ``1234.56``
    - ``"36,50"`` → ``36.5``
    - ``"1.000"`` → ``1000.0``
    - ``"1.5"`` → ``1.5`` (plain float passthrough)

    Returns ``None`` for ``"—"`` / ``""`` placeholders and raises
    ``ValueError`` when the string cannot be parsed as a number.
    """
    cleaned = raw.replace("Bs.", "").replace("$", "").strip()
    if cleaned in ("—", ""):
        return None
    if "," in cleaned:
        # Comma is the decimal separator: strip thousands dots first.
        return float(cleaned.replace(".", "").replace(",", "."))
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", cleaned):
        # Thousands separator without decimals: "1.000" -> 1000.0
        return float(cleaned.replace(".", ""))
    return float(cleaned)


def _write_cell_value(
    cell: Any,
    raw: str,
    header: str,
) -> None:
    """Write a value into a cell, auto-detecting numeric/currency types."""
    cell.value = raw

    # Try to parse as number (strip Bs. prefix, $, spaces)
    try:
        num = _to_number(raw)
    except ValueError, TypeError:
        return  # keep original string

    if num is None:
        return  # keep "—" / "" placeholders as-is

    cell.value = num
    hl = header.lower()
    if any(kw in hl for kw in CURRENCY_HINTS):
        cell.number_format = "#,##0.00"
    elif any(kw in hl for kw in INTEGER_HINTS):
        cell.number_format = "#,##0"
