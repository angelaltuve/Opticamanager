"""Tests for the invoice preview dialog (receipt_dialog)."""

from __future__ import annotations

from pathlib import Path

from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot
from PyQt6.QtGui import QPageSize, QPainter, QPdfWriter
from PyQt6.QtWidgets import QDialog

from opticamanager.ui.widgets import receipt_dialog
from opticamanager.ui.widgets.receipt_dialog import ReceiptDialog


def _write_mini_pdf(path: Path) -> Path:
    """Write a one-page PDF via QPdfWriter, the preview must load it."""
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    painter = QPainter(writer)
    painter.drawText(50, 100, "Factura de prueba")
    painter.end()
    return path


class TestReceiptDialogPreview:
    def _build_dialog(
        self, qtbot: QtBot, mocker: MockerFixture, lineas: list[str] | None = None
    ) -> ReceiptDialog:
        mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.generate_sale_receipt",
            side_effect=lambda _sale_id, path: _write_mini_pdf(path),
        )
        dialogo = ReceiptDialog(1, None, lineas=lineas)
        qtbot.addWidget(dialogo)
        return dialogo

    def test_vista_previa_carga_pdf(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        dialogo = self._build_dialog(qtbot, mocker)

        assert dialogo._pdf_doc is not None
        assert dialogo._pdf_doc.pageCount() == 1
        assert not dialogo._fallback.isVisible()
        assert dialogo._preview.document() is dialogo._pdf_doc

    def test_resumen_se_muestra_en_etiqueta(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        lineas = ["Factura: FAC-000001", "Total: Bs 100,00"]
        dialogo = self._build_dialog(qtbot, mocker, lineas=lineas)

        assert dialogo._summary.text() == "\n".join(lineas)

    def test_vista_previa_fallida_muestra_fallback(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.generate_sale_receipt",
            side_effect=RuntimeError("sin datos"),
        )
        dialogo = ReceiptDialog(1, None)
        qtbot.addWidget(dialogo)
        dialogo.show()

        assert dialogo._pdf_doc is None
        assert not dialogo._preview.isVisible()
        assert dialogo._fallback.isVisible()


class TestReceiptDialogGuardarPdf:
    def _build_dialog(self, qtbot: QtBot, mocker: MockerFixture) -> ReceiptDialog:
        mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.generate_sale_receipt",
            side_effect=lambda _sale_id, path: _write_mini_pdf(path),
        )
        dialogo = ReceiptDialog(1, None)
        qtbot.addWidget(dialogo)
        return dialogo

    def test_guardar_genera_pdf_en_ruta_elegida(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        dialogo = self._build_dialog(qtbot, mocker)
        generate = mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.generate_sale_receipt"
        )
        mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.suggest_sale_receipt_path",
            return_value=Path("/tmp/factura.pdf"),
        )
        mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.QFileDialog.getSaveFileName",
            return_value=("/tmp/recibo.pdf", "PDF (*.pdf)"),
        )
        informacion = mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.dialogo_informacion"
        )

        dialogo.guardar_pdf()

        generate.assert_called_once_with(1, "/tmp/recibo.pdf")
        informacion.assert_called_once()

    def test_guardar_cancelado_no_genera(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        dialogo = self._build_dialog(qtbot, mocker)
        generate = mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.generate_sale_receipt"
        )
        mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.suggest_sale_receipt_path",
            return_value=Path("/tmp/factura.pdf"),
        )
        mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.QFileDialog.getSaveFileName",
            return_value=("", ""),
        )

        dialogo.guardar_pdf()

        generate.assert_not_called()

    def test_guardar_error_al_sugerir_ruta_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        dialogo = self._build_dialog(qtbot, mocker)
        mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.suggest_sale_receipt_path",
            side_effect=RuntimeError("sin carpeta"),
        )
        error = mocker.patch("opticamanager.ui.widgets.receipt_dialog.dialogo_error")

        dialogo.guardar_pdf()

        error.assert_called_once()

    def test_guardar_error_al_generar_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        dialogo = self._build_dialog(qtbot, mocker)
        mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.generate_sale_receipt",
            side_effect=RuntimeError("sin permisos"),
        )
        mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.suggest_sale_receipt_path",
            return_value=Path("/tmp/factura.pdf"),
        )
        mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.QFileDialog.getSaveFileName",
            return_value=("/tmp/recibo.pdf", "PDF (*.pdf)"),
        )
        error = mocker.patch("opticamanager.ui.widgets.receipt_dialog.dialogo_error")

        dialogo.guardar_pdf()

        error.assert_called_once()


class TestReceiptDialogImprimir:
    def _build_mocked_printer_dialog(
        self, mocker: MockerFixture, resultado: QDialog.DialogCode
    ) -> tuple[object, object]:
        dlg = mocker.patch("opticamanager.ui.widgets.receipt_dialog.QPrintDialog")
        dlg.return_value.exec.return_value = resultado
        render = mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.render_sale_receipt"
        )
        return dlg, render

    def test_imprimir_aceptado_pinta_sobre_el_printer(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.generate_sale_receipt",
            side_effect=lambda _sale_id, path: _write_mini_pdf(path),
        )
        dialogo = ReceiptDialog(1, None)
        qtbot.addWidget(dialogo)
        dlg, render = self._build_mocked_printer_dialog(
            mocker, QDialog.DialogCode.Accepted
        )

        dialogo.imprimir()

        render.assert_called_once()
        printer_entregado = dlg.call_args.args[0]
        render.assert_called_once_with(printer_entregado, 1)

    def test_imprimir_cancelado_no_pinta(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.generate_sale_receipt",
            side_effect=lambda _sale_id, path: _write_mini_pdf(path),
        )
        dialogo = ReceiptDialog(1, None)
        qtbot.addWidget(dialogo)
        _dlg, render = self._build_mocked_printer_dialog(
            mocker, QDialog.DialogCode.Rejected
        )

        dialogo.imprimir()

        render.assert_not_called()

    def test_imprimir_error_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.generate_sale_receipt",
            side_effect=lambda _sale_id, path: _write_mini_pdf(path),
        )
        dialogo = ReceiptDialog(1, None)
        qtbot.addWidget(dialogo)
        dlg = mocker.patch("opticamanager.ui.widgets.receipt_dialog.QPrintDialog")
        dlg.return_value.exec.return_value = QDialog.DialogCode.Accepted
        mocker.patch(
            "opticamanager.ui.widgets.receipt_dialog.render_sale_receipt",
            side_effect=RuntimeError("impresora apagada"),
        )
        error = mocker.patch("opticamanager.ui.widgets.receipt_dialog.dialogo_error")

        dialogo.imprimir()

        error.assert_called_once()


class TestShowSaleReceipt:
    def test_abre_dialogo_modal(self, mocker: MockerFixture) -> None:
        clase = mocker.patch("opticamanager.ui.widgets.receipt_dialog.ReceiptDialog")

        receipt_dialog.show_sale_receipt(None, 5, lineas=["x"], titulo="Factura")

        clase.assert_called_once_with(5, None, lineas=["x"], titulo="Factura")
        clase.return_value.exec.assert_called_once_with()
