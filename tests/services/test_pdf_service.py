"""Tests for the PDF generation service (pdf_service)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainter, QPageSize
from PyQt6.QtPrintSupport import QPrinter

from opticamanager.models.customer import Customer
from opticamanager.models.prescription import Prescription
from opticamanager.models.sale import Sale
from opticamanager.models.sale_detail import SaleDetail
from opticamanager.models.user import User
from opticamanager.services import pdf_service


def _make_customer() -> MagicMock:
    customer = MagicMock(spec=Customer)
    customer.id = 1
    customer.name = "Ana Gómez"
    customer.id_document = "V-12345678"
    return customer


def _make_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = 1
    user.name = "Admin User"
    return user


def _make_sale() -> MagicMock:
    sale = MagicMock(spec=Sale)
    sale.id = 1
    sale.invoice_number = "FAC-000001"
    sale.customer_id = 1
    sale.user_id = 1
    sale.status_id = 1
    sale.payment_method = "Efectivo"
    sale.amount_received = Decimal("100.00")
    sale.change_amount = Decimal("0.00")
    sale.subtotal = Decimal("86.21")
    sale.taxes = Decimal("13.79")
    sale.discount = Decimal("0.00")
    sale.total = Decimal("100.00")
    sale.created_at = datetime(2026, 9, 20, 10, 30)

    product = MagicMock()
    product.name = "Lentes progresivos"
    detalle = MagicMock(spec=SaleDetail)
    detalle.quantity = 1
    detalle.unit_price = Decimal("86.21")
    detalle.subtotal = Decimal("86.21")
    detalle.product = product
    sale.details = [detalle]
    return sale


def _make_prescription() -> MagicMock:
    rx = MagicMock(spec=Prescription)
    rx.id = 7
    rx.customer_id = 1
    rx.issued_date = date(2026, 9, 20)
    rx.od_sphere = Decimal("-1.25")
    rx.od_cylinder = Decimal("-0.50")
    rx.od_axis = 90
    rx.od_addition = None
    rx.os_sphere = None
    rx.os_cylinder = None
    rx.os_axis = None
    rx.os_addition = Decimal("2.00")
    rx.pupillary_distance = Decimal("62.0")
    rx.notes = "Revisión anual"
    return rx


def _patch_session(mocker: MockerFixture, mapping: dict) -> MagicMock:
    """Return a fake SessionManager whose get() resolves by (model, id)."""
    manager = mocker.patch("opticamanager.services.pdf_service.SessionManager")
    fake = MagicMock()
    fake.get.side_effect = lambda model, ident: mapping.get(model, {}).get(ident)
    manager.return_value.__enter__.return_value = fake
    return fake


class TestGenerateSaleReceipt:
    def test_crea_pdf_valido(self, qapp, mocker: MockerFixture, tmp_path: Path) -> None:
        _patch_session(
            mocker,
            {
                Sale: {1: _make_sale()},
                Customer: {1: _make_customer()},
                User: {1: _make_user()},
            },
        )
        mocker.patch(
            "opticamanager.services.pdf_service.get_iva_rate_pct", return_value=16
        )

        out = tmp_path / "recibo.pdf"
        result = pdf_service.generate_sale_receipt(1, out)

        assert result == out.resolve()
        assert out.is_file()
        assert out.stat().st_size > 0
        assert out.read_bytes()[:4] == b"%PDF"

    def test_venta_inexistente_lanza_value_error(
        self, qapp, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        _patch_session(mocker, {Sale: {}})

        with pytest.raises(ValueError, match="Sale #999"):
            pdf_service.generate_sale_receipt(999, tmp_path / "recibo.pdf")


class TestDrawTextMetrics:
    """Regression: line advance must come from real font metrics.

    A fixed ``font_size + 8`` px advance made every line and column overlap in
    the generated PDF at 300 and 1200 DPI.
    """

    def test_avance_de_linea_usa_metricas_reales(self, qapp, tmp_path: Path) -> None:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setResolution(300)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(tmp_path / "metricas.pdf"))
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))

        painter = QPainter(printer)
        try:
            y_start = pdf_service.MARGIN
            y_end = pdf_service._draw_text(
                painter, "Prueba de métricas", pdf_service.MARGIN, y_start
            )
        finally:
            painter.end()

        advance = y_end - y_start
        # At 300 DPI a 14pt line measures about 58px tall, so the fixed 22px
        # advance (font_size + 8) was too small and made lines overlap.
        assert advance >= 50
        assert advance > pdf_service.FONT_SIZE_NORMAL

    def test_columnas_de_items_no_se_pisan(
        self, qapp, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """The product name stays left of 'Cant.' and 'Cant.' must not share an
        X with 'Producto' (col_x regression)."""
        _patch_session(
            mocker,
            {
                Sale: {1: _make_sale()},
                Customer: {1: _make_customer()},
                User: {1: _make_user()},
            },
        )
        mocker.patch(
            "opticamanager.services.pdf_service.get_iva_rate_pct", return_value=16
        )

        calls: list[tuple[float, str]] = []

        def _capture(rect, _flags: int, text: str) -> None:
            calls.append((rect.left(), text))

        mocker.patch.object(QPainter, "drawText", side_effect=_capture)

        pdf_service.generate_sale_receipt(1, tmp_path / "recibo.pdf")

        x_producto = next(x for x, t in calls if t == "Producto")
        x_product = next(x for x, t in calls if t == "Lentes progresivos")
        x_cant = next(x for x, t in calls if t == "Cant.")
        x_precio = next(x for x, t in calls if t == "Precio")

        assert x_cant > x_producto
        assert x_product < x_cant
        assert x_precio > x_cant

    def test_cabecera_items_en_una_sola_fila(
        self, qapp, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """Regression: the 4 table headers share a Y (a single row) and data row
        1 starts strictly below the header."""
        _patch_session(
            mocker,
            {
                Sale: {1: _make_sale()},
                Customer: {1: _make_customer()},
                User: {1: _make_user()},
            },
        )
        mocker.patch(
            "opticamanager.services.pdf_service.get_iva_rate_pct", return_value=16
        )

        calls: list[tuple[QRectF, str]] = []

        def _capture(rect, _flags: int, text: str) -> None:
            calls.append((rect, text))

        mocker.patch.object(QPainter, "drawText", side_effect=_capture)

        pdf_service.generate_sale_receipt(1, tmp_path / "recibo.pdf")

        ys = {text: rect.y() for rect, text in calls}
        assert ys["Producto"] == ys["Cant."] == ys["Precio"] == ys["Subtotal"]
        assert ys["Lentes progresivos"] > ys["Cant."]

    def test_nombre_largo_se_envuelve_sin_invadir_columnas(
        self, qapp, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """A long product name wraps inside its own column: it neither crosses
        'Cant.' (by X) nor overflows its row (values stay centred)."""
        largo = "Lentes de Sol Vintage - Ray-Ban Aviator"
        sale = _make_sale()
        sale.details[0].product.name = largo
        _patch_session(
            mocker,
            {
                Sale: {1: sale},
                Customer: {1: _make_customer()},
                User: {1: _make_user()},
            },
        )
        mocker.patch(
            "opticamanager.services.pdf_service.get_iva_rate_pct", return_value=16
        )

        calls: list[tuple[QRectF, str]] = []

        def _capture(rect, _flags: int, text: str) -> None:
            calls.append((rect, text))

        mocker.patch.object(QPainter, "drawText", side_effect=_capture)

        pdf_service.generate_sale_receipt(1, tmp_path / "recibo.pdf")

        rect_nombre = next(rect for rect, text in calls if text == largo)
        # The wrapped block stays within the right edge of its column
        # (col_x[1] = MARGIN + 900), so it never touches 'Cant.'.
        assert rect_nombre.right() <= pdf_service.MARGIN + 900
        # It spans more than one line (wrapping is active)...
        assert rect_nombre.height() > pdf_service.FONT_SIZE_NORMAL * 2
        # ...and the row values are centred inside the block.
        y_qty = next(rect.y() for rect, text in calls if text == "1")
        assert rect_nombre.y() <= y_qty < rect_nombre.bottom()


class TestGeneratePrescription:
    def test_crea_pdf_valido(self, qapp, mocker: MockerFixture, tmp_path: Path) -> None:
        _patch_session(
            mocker,
            {Prescription: {7: _make_prescription()}, Customer: {1: _make_customer()}},
        )

        out = tmp_path / "receta.pdf"
        result = pdf_service.generate_prescription(7, out)

        assert result == out.resolve()
        assert out.is_file()
        assert out.stat().st_size > 0
        assert out.read_bytes()[:4] == b"%PDF"

    def test_receta_inexistente_lanza_value_error(
        self, qapp, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        _patch_session(mocker, {Prescription: {}})

        with pytest.raises(ValueError, match="Prescription #42"):
            pdf_service.generate_prescription(42, tmp_path / "receta.pdf")


class TestSuggestPaths:
    def test_sugiere_recibo_con_cliente(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        _patch_session(
            mocker, {Sale: {1: _make_sale()}, Customer: {1: _make_customer()}}
        )
        mocker.patch.object(pdf_service, "RECEIPTS_DIR", tmp_path / "facturas")

        suggested = pdf_service.suggest_sale_receipt_path(1)

        assert suggested == tmp_path / "facturas" / "factura_FAC-000001_ana_gomez.pdf"
        assert suggested.parent.is_dir()

    def test_sugiere_recibo_sin_cliente(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        _patch_session(mocker, {Sale: {1: _make_sale()}})
        mocker.patch.object(pdf_service, "RECEIPTS_DIR", tmp_path / "facturas")

        suggested = pdf_service.suggest_sale_receipt_path(1)

        assert suggested.name == "factura_FAC-000001.pdf"
        assert suggested.parent.is_dir()

    def test_sugiere_receta_con_paciente(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        _patch_session(
            mocker,
            {Prescription: {7: _make_prescription()}, Customer: {1: _make_customer()}},
        )
        mocker.patch.object(pdf_service, "PRESCRIPTIONS_DIR", tmp_path / "recetas")

        suggested = pdf_service.suggest_prescription_path(7)

        assert suggested == tmp_path / "recetas" / "receta_ana_gomez_2026-09-20.pdf"
        assert suggested.parent.is_dir()

    def test_sugiere_receta_sin_paciente(
        self, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        _patch_session(mocker, {Prescription: {7: _make_prescription()}})
        mocker.patch.object(pdf_service, "PRESCRIPTIONS_DIR", tmp_path / "recetas")

        suggested = pdf_service.suggest_prescription_path(7)

        assert suggested.name == "receta_7.pdf"
        assert suggested.parent.is_dir()


class TestSlugify:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Ana Gómez", "ana_gomez"),
            ("José Pérez-López", "jose_perez_lopez"),
            ("   María  Luisa   ", "maria_luisa"),
            ("C/Alberto, 12", "c_alberto_12"),
            ("", "sin_nombre"),
            (None, "sin_nombre"),
        ],
    )
    def test_slugify(self, raw: str | None, expected: str) -> None:
        assert pdf_service._slugify(raw) == expected


class TestRenderSaleReceipt:
    """Paint the receipt onto a real QPrinter (PDF format)."""

    def test_pinta_comprobante_en_printer_pdf(
        self, qapp, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        _patch_session(
            mocker,
            {
                Sale: {1: _make_sale()},
                Customer: {1: _make_customer()},
                User: {1: _make_user()},
            },
        )
        mocker.patch(
            "opticamanager.services.pdf_service.get_iva_rate_pct", return_value=16
        )

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(tmp_path / "impresion.pdf"))

        calls: list[str] = []

        def _capture(rect, _flags: int, text: str) -> None:
            calls.append(text)

        mocker.patch.object(QPainter, "drawText", side_effect=_capture)

        pdf_service.render_sale_receipt(printer, 1)

        assert "COMPROBANTE DE VENTA" in calls
        out = tmp_path / "impresion.pdf"
        assert out.is_file()
        assert out.read_bytes()[:4] == b"%PDF"

    def test_venta_inexistente_lanza_value_error(
        self, qapp, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        _patch_session(mocker, {Sale: {}})

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(tmp_path / "impresion.pdf"))

        with pytest.raises(ValueError, match="Sale #999"):
            pdf_service.render_sale_receipt(printer, 999)
