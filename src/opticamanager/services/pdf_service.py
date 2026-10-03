"""PDF generation service for sales receipts and prescriptions.

Uses PyQt6 QPrinter + QPainter (no external dependencies).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QFont, QFontMetricsF, QPainter, QPageSize, QPen
from PyQt6.QtPrintSupport import QPrinter

from opticamanager.core.logging_config import get_logger
from opticamanager.services.settings_service import get_iva_rate_pct
from opticamanager.db import SessionManager
from opticamanager.models.customer import Customer
from opticamanager.models.prescription import Prescription
from opticamanager.models.sale import Sale
from opticamanager.models.sale_detail import SaleDetail
from opticamanager.models.user import User

log = get_logger(__name__)

# ── Layout constants ──────────────────────────────────────────────

PAGE_WIDTH = 2480  # ~210mm at 300 DPI (A4 width)
MARGIN = 120
COL_WIDTH = PAGE_WIDTH - 2 * MARGIN
LINE_HEIGHT = 50
FONT_SIZE_TITLE = 28
FONT_SIZE_HEADER = 18
FONT_SIZE_NORMAL = 14
FONT_SIZE_SMALL = 11

BUSINESS_NAME = "OpticaManager"
BUSINESS_TAGLINE = "Sistema de Gestión Óptica"

# Default destination folders for saved PDFs (created on demand).
DOCUMENTS_DIR = Path.home() / "Documents" / "OpticaManager"
RECEIPTS_DIR = DOCUMENTS_DIR / "facturas"
PRESCRIPTIONS_DIR = DOCUMENTS_DIR / "recetas"


# ── Helpers ───────────────────────────────────────────────────────


def _draw_text(
    painter: QPainter,
    text: str,
    x: int,
    y: int,
    font_size: int = FONT_SIZE_NORMAL,
    bold: bool = False,
    align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
    width: int = COL_WIDTH,
) -> int:
    """Draw text and return the Y position after the line."""
    font = QFont("DejaVu Sans", font_size)
    font.setBold(bold)
    painter.setFont(font)

    # Use real font metrics on the paint device (300 DPI printer), so lines
    # advance by the actual glyph height instead of a fixed pixel estimate.
    metrics = QFontMetricsF(font, painter.device())
    rect = QRectF(x, y, width, metrics.height())
    painter.drawText(rect, int(align | Qt.AlignmentFlag.AlignVCenter), text)
    return y + int(metrics.lineSpacing()) + 8


def _line_advance(painter: QPainter, font_size: int) -> int:
    """Return the real on-device line advance for a font size (no drawing)."""
    font = QFont("DejaVu Sans", font_size)
    return int(QFontMetricsF(font, painter.device()).lineSpacing()) + 8


def _draw_wrapped_text(
    painter: QPainter,
    text: str,
    x: int,
    y: int,
    font_size: int = FONT_SIZE_NORMAL,
    width: int = COL_WIDTH,
) -> int:
    """Draw text word-wrapped inside ``width``; return Y after the block."""
    font = QFont("DejaVu Sans", font_size)
    painter.setFont(font)
    metrics = QFontMetricsF(font, painter.device())
    wrap_flags = int(Qt.TextFlag.TextWordWrap)
    block_rect = metrics.boundingRect(QRectF(x, y, width, 10_000), wrap_flags, text)
    block_height = max(metrics.height(), block_rect.height())
    painter.drawText(QRectF(x, y, width, block_height), wrap_flags, text)
    return y + int(block_height)


def _draw_line(painter: QPainter, x: int, y: int, width: int = COL_WIDTH) -> int:
    """Draw a horizontal separator line and return the next Y position."""
    pen = QPen(painter.pen().color(), 1)
    painter.setPen(pen)
    painter.drawLine(x, y, x + width, y)
    return y + LINE_HEIGHT


def _draw_header(painter: QPainter, title: str, y: int) -> int:
    """Draw the standard document header (business name + title)."""
    y = _draw_text(
        painter,
        BUSINESS_NAME,
        MARGIN,
        y,
        font_size=FONT_SIZE_TITLE,
        bold=True,
        align=Qt.AlignmentFlag.AlignHCenter,
        width=COL_WIDTH,
    )
    y = _draw_text(
        painter,
        BUSINESS_TAGLINE,
        MARGIN,
        y,
        font_size=FONT_SIZE_SMALL,
        align=Qt.AlignmentFlag.AlignHCenter,
        width=COL_WIDTH,
    )
    y = _draw_line(painter, MARGIN, y)
    y = _draw_text(
        painter,
        title,
        MARGIN,
        y,
        font_size=FONT_SIZE_HEADER,
        bold=True,
        align=Qt.AlignmentFlag.AlignHCenter,
        width=COL_WIDTH,
    )
    y = _draw_line(painter, MARGIN, y)
    return y + LINE_HEIGHT // 2


def _draw_footer(painter: QPainter, y: int) -> int:
    """Draw the standard footer."""
    y = _draw_line(painter, MARGIN, y)
    y += LINE_HEIGHT // 2
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    y = _draw_text(
        painter,
        f"Generado: {now_str}",
        MARGIN,
        y,
        font_size=FONT_SIZE_SMALL,
        align=Qt.AlignmentFlag.AlignHCenter,
        width=COL_WIDTH,
    )
    return _draw_text(
        painter,
        "Gracias por su preferencia",
        MARGIN,
        y,
        font_size=FONT_SIZE_NORMAL,
        bold=False,
        align=Qt.AlignmentFlag.AlignHCenter,
        width=COL_WIDTH,
    )


def _fmt_opt(value: Decimal | None, unit: str = "") -> str:
    """Format an optical value for display."""
    if value is None:
        return "—"
    return f"{value:,.2f}{unit}"


def _slugify(text: str) -> str:
    """Normalize a label into a filesystem-safe slug.

    Lowercases, strips accents and replaces every non-alphanumeric run
    with a single underscore (e.g. "Ana Gómez" -> "ana_gomez").
    """
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_only = "".join(c for c in normalized if not unicodedata.combining(c))
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_only).strip("_").lower()
    return slug or "sin_nombre"


def _ensure_dir(path: Path) -> None:
    """Create the parent directory of a target path if missing."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise OSError(f"No se pudo crear el directorio para el PDF: {e}") from e


def _load_sale_receipt_data(
    sale_id: int,
) -> tuple[Sale, Customer | None, User | None, list[SaleDetail]]:
    """Load a sale and its eager-loaded relationships for receipt rendering."""
    with SessionManager() as session:
        sale = session.get(Sale, sale_id)
        if not sale:
            raise ValueError(f"Sale #{sale_id} not found")

        # Eager-load relationships (including SaleDetail.product)
        customer = session.get(Customer, sale.customer_id)
        user = session.get(User, sale.user_id)
        details: list[SaleDetail] = sale.details  # type: ignore[assignment]
        for d in details:
            _ = d.product  # force lazy load while session is open
    return sale, customer, user, details


def _configure_receipt_printer(printer: QPrinter) -> None:
    """Normalize a printer to the 300 DPI A4 canvas the layout targets.

    Layout constants are designed for a 300 DPI canvas (A4 = 2480x3508 px).
    Without this, QPrinter PDF renders at 1200 DPI and text (sized in
    points) overlaps the pixel-based coordinates.
    """
    printer.setResolution(300)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))


def _render_sale_receipt(
    painter: QPainter,
    sale: Sale,
    customer: Customer | None,
    user: User | None,
    details: list[SaleDetail],
) -> None:
    """Paint the full receipt document onto an open painter."""

    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    y = MARGIN

    # ── Header ──
    y = _draw_header(painter, "COMPROBANTE DE VENTA", y)

    # ── Info block ──
    y = _draw_text(
        painter,
        f"Factura: {sale.invoice_number}",
        MARGIN,
        y,
        bold=True,
    )
    created = sale.created_at.strftime("%d/%m/%Y %H:%M") if sale.created_at else "—"
    y = _draw_text(painter, f"Fecha: {created}", MARGIN, y, font_size=FONT_SIZE_SMALL)
    y = _draw_text(
        painter,
        f"Cliente: {customer.name if customer else '—'} ({customer.id_document if customer else '—'})",
        MARGIN,
        y,
        font_size=FONT_SIZE_SMALL,
    )
    y = _draw_text(
        painter,
        f"Atendido por: {user.name if user else '—'}",
        MARGIN,
        y,
        font_size=FONT_SIZE_SMALL,
    )

    y += LINE_HEIGHT // 2
    y = _draw_line(painter, MARGIN, y)

    # ── Items table header ──
    col_x = [MARGIN, MARGIN + 900, MARGIN + 1300, MARGIN + 1700]
    col_w = [col_x[1] - col_x[0], 380, 400, COL_WIDTH - col_x[3]]

    # All four header labels share a single row: draw them at the same Y
    # (do not advance between them). Then advance by one real SMALL line
    # so the first data row starts strictly below the header text.
    header_y = y
    for label, hx in zip(
        ("Producto", "Cant.", "Precio", "Subtotal"), col_x, strict=True
    ):
        _draw_text(
            painter,
            label,
            hx,
            header_y,
            font_size=FONT_SIZE_SMALL,
            bold=True,
        )
    y = header_y + _line_advance(painter, FONT_SIZE_SMALL) + LINE_HEIGHT // 2

    # Items
    for d in details:
        product_name = d.product.name if d.product else f"ID#{d.product_id}"
        y_prev = y
        # Wrap long names inside the Product column so they never invade
        # the adjacent columns; the row grows to fit the wrapped block.
        y = _draw_wrapped_text(
            painter,
            product_name,
            col_x[0],
            y_prev,
            font_size=FONT_SIZE_NORMAL,
            width=col_w[0] - 20,
        )
        row_height = y - y_prev
        # Vertically center the value columns within the (wrapped) row.
        value_y = y_prev + (row_height - _line_advance(painter, FONT_SIZE_NORMAL)) // 2
        _draw_text(
            painter,
            str(d.quantity),
            col_x[1],
            value_y,
            font_size=FONT_SIZE_NORMAL,
            width=col_w[1],
        )
        _draw_text(
            painter,
            f"Bs. {d.unit_price:,.2f}",
            col_x[2],
            value_y,
            font_size=FONT_SIZE_NORMAL,
            width=col_w[2],
        )
        _draw_text(
            painter,
            f"Bs. {d.subtotal:,.2f}",
            col_x[3],
            value_y,
            font_size=FONT_SIZE_NORMAL,
            width=col_w[3],
        )
        y = y_prev + row_height

    y += LINE_HEIGHT // 2
    y = _draw_line(painter, MARGIN, y)

    # ── Totals ──
    y = _draw_text(
        painter,
        f"Subtotal:                        Bs. {sale.subtotal:,.2f}",
        MARGIN,
        y,
    )
    y = _draw_text(
        painter,
        f"IVA ({get_iva_rate_pct()}%):                        Bs. {sale.taxes:,.2f}",
        MARGIN,
        y,
    )

    if sale.discount and sale.discount > 0:
        y = _draw_text(
            painter,
            f"Descuento:                      Bs. {sale.discount:,.2f}",
            MARGIN,
            y,
        )

    y += LINE_HEIGHT // 2
    y = _draw_text(
        painter,
        f"TOTAL:                            Bs. {sale.total:,.2f}",
        MARGIN,
        y,
        bold=True,
        font_size=FONT_SIZE_HEADER,
    )
    y = _draw_line(painter, MARGIN, y)
    y += LINE_HEIGHT // 2

    # ── Payment info ──
    y = _draw_text(
        painter,
        f"Método de pago: {sale.payment_method}",
        MARGIN,
        y,
        bold=False,
    )
    if sale.amount_received is not None:
        y = _draw_text(
            painter,
            f"Recibido:       Bs. {sale.amount_received:,.2f}",
            MARGIN,
            y,
        )
    if sale.change_amount is not None and sale.change_amount > 0:
        y = _draw_text(
            painter,
            f"Cambio:         Bs. {sale.change_amount:,.2f}",
            MARGIN,
            y,
        )

    # ── Footer ──
    y += LINE_HEIGHT
    _draw_footer(painter, y)


def render_sale_receipt(printer: QPrinter, sale_id: int) -> None:
    """Paint a sale receipt onto an existing printer.

    Used by the direct-print and preview paths. Normalizes the printer to
    the 300 DPI A4 canvas so the layout matches the generated PDF.

    Args:
        printer: Target printer (native print job or PDF writer).
        sale_id: Primary key of the Sale record.

    Raises:
        ValueError: If no Sale with that id exists.
    """
    sale, customer, user, details = _load_sale_receipt_data(sale_id)
    _configure_receipt_printer(printer)
    painter = QPainter(printer)
    try:
        _render_sale_receipt(painter, sale, customer, user, details)
    finally:
        painter.end()


def generate_sale_receipt(sale_id: int, output_path: str | Path) -> Path:
    """Generate a PDF sales receipt/invoice.

    Args:
        sale_id: Primary key of the Sale record.
        output_path: Full path where the PDF will be saved.

    Returns:
        The resolved Path to the generated PDF file.
    """
    output = Path(output_path)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise OSError(f"No se pudo crear el directorio para el PDF: {e}") from e

    sale, customer, user, details = _load_sale_receipt_data(sale_id)

    try:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        _configure_receipt_printer(printer)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(output.resolve()))
    except Exception as e:
        raise RuntimeError(
            f"No se pudo configurar la impresora para el PDF: {e}"
        ) from e

    painter = QPainter(printer)
    try:
        _render_sale_receipt(painter, sale, customer, user, details)
    finally:
        painter.end()

    log.info("PDF receipt generated: %s", output.resolve())
    return output.resolve()


# ── Public API ──


def generate_prescription(prescription_id: int, output_path: str | Path) -> Path:
    """Generate a PDF prescription document.

    Args:
        prescription_id: Primary key of the Prescription record.
        output_path: Full path where the PDF will be saved.

    Returns:
        The resolved Path to the generated PDF file.
    """
    output = Path(output_path)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise OSError(f"No se pudo crear el directorio para el PDF: {e}") from e

    with SessionManager() as session:
        rx = session.get(Prescription, prescription_id)
        if not rx:
            raise ValueError(f"Prescription #{prescription_id} not found")

        customer = session.get(Customer, rx.customer_id)

    try:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        # Layout constants are designed for a 300 DPI canvas (A4 = 2480x3508 px).
        # Without this, QPrinter PDF renders at 1200 DPI and text (sized in
        # points) overlaps the pixel-based coordinates.
        printer.setResolution(300)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(output.resolve()))
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    except Exception as e:
        raise RuntimeError(
            f"No se pudo configurar la impresora para el PDF: {e}"
        ) from e

    painter = QPainter(printer)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = MARGIN

        # ── Header ──
        y = _draw_header(painter, "RECETA ÓPTICA", y)

        # ── Patient info ──
        y = _draw_text(
            painter,
            f"Paciente: {customer.name if customer else '—'} ({customer.id_document if customer else '—'})",
            MARGIN,
            y,
            bold=True,
        )
        y = _draw_text(
            painter,
            f"Fecha de emisión: {rx.issued_date.isoformat()}",
            MARGIN,
            y,
            font_size=FONT_SIZE_SMALL,
        )

        y += LINE_HEIGHT
        y = _draw_line(painter, MARGIN, y)

        # ── OD (Right eye) ──
        y = _draw_text(
            painter,
            "OJO DERECHO (OD)",
            MARGIN,
            y,
            bold=True,
            font_size=FONT_SIZE_HEADER,
        )
        y = _draw_text(
            painter,
            f"  Esfera (SPH):    {_fmt_opt(rx.od_sphere)}",
            MARGIN,
            y,
        )
        y = _draw_text(
            painter,
            f"  Cilindro (CYL):  {_fmt_opt(rx.od_cylinder)}",
            MARGIN,
            y,
        )
        y = _draw_text(
            painter,
            f"  Eje (AXIS):      {rx.od_axis if rx.od_axis is not None else '—'}",
            MARGIN,
            y,
        )
        y = _draw_text(
            painter,
            f"  Adición (ADD):   {_fmt_opt(rx.od_addition)}",
            MARGIN,
            y,
        )

        y += LINE_HEIGHT // 2
        y = _draw_line(painter, MARGIN, y)

        # ── OS (Left eye) ──
        y = _draw_text(
            painter,
            "OJO IZQUIERDO (OI)",
            MARGIN,
            y,
            bold=True,
            font_size=FONT_SIZE_HEADER,
        )
        y = _draw_text(
            painter,
            f"  Esfera (SPH):    {_fmt_opt(rx.os_sphere)}",
            MARGIN,
            y,
        )
        y = _draw_text(
            painter,
            f"  Cilindro (CYL):  {_fmt_opt(rx.os_cylinder)}",
            MARGIN,
            y,
        )
        y = _draw_text(
            painter,
            f"  Eje (AXIS):      {rx.os_axis if rx.os_axis is not None else '—'}",
            MARGIN,
            y,
        )
        y = _draw_text(
            painter,
            f"  Adición (ADD):   {_fmt_opt(rx.os_addition)}",
            MARGIN,
            y,
        )

        y += LINE_HEIGHT // 2
        y = _draw_line(painter, MARGIN, y)

        # ── DP & Notes ──
        y = _draw_text(
            painter,
            f"Distancia Pupilar (DP):  {_fmt_opt(rx.pupillary_distance, ' mm')}",
            MARGIN,
            y,
            bold=True,
        )

        if rx.notes:
            y += LINE_HEIGHT // 2
            y = _draw_text(
                painter,
                "Notas:",
                MARGIN,
                y,
                bold=True,
            )
            y = _draw_text(
                painter,
                rx.notes,
                MARGIN + 20,
                y,
                font_size=FONT_SIZE_NORMAL,
                width=COL_WIDTH - 20,
            )

        # ── Footer ──
        y += LINE_HEIGHT
        _draw_footer(painter, y)

    finally:
        painter.end()

    log.info("PDF prescription generated: %s", output.resolve())
    return output.resolve()


def suggest_sale_receipt_path(sale_id: int) -> Path:
    """Build the suggested save path for a sale receipt PDF.

    Creates the destination folder if needed so the save dialog opens
    there. Example:
    ~/Documents/OpticaManager/facturas/factura_FAC-000001_ana_gomez.pdf

    Raises:
        ValueError: if the Sale does not exist.
    """
    with SessionManager() as session:
        sale = session.get(Sale, sale_id)
        customer = session.get(Customer, sale.customer_id) if sale else None
    if sale is None:
        raise ValueError(f"Sale #{sale_id} not found")

    name = f"factura_{sale.invoice_number}"
    if customer and customer.name:
        name += f"_{_slugify(customer.name)}"
    path = RECEIPTS_DIR / f"{name}.pdf"
    _ensure_dir(path)
    return path


def suggest_prescription_path(rx_id: int) -> Path:
    """Build the suggested save path for a prescription PDF.

    Creates the destination folder if needed so the save dialog opens
    there. Example:
    ~/Documents/OpticaManager/recetas/receta_ana_gomez_2026-09-20.pdf

    Raises:
        ValueError: if the Prescription does not exist.
    """
    with SessionManager() as session:
        rx = session.get(Prescription, rx_id)
        customer = session.get(Customer, rx.customer_id) if rx else None
    if rx is None:
        raise ValueError(f"Prescription #{rx_id} not found")

    if customer and customer.name:
        name = f"receta_{_slugify(customer.name)}_{rx.issued_date.isoformat()}"
    else:
        name = f"receta_{rx_id}"
    path = PRESCRIPTIONS_DIR / f"{name}.pdf"
    _ensure_dir(path)
    return path
