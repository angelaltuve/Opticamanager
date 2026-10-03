"""Invoice preview dialog shown after a POS sale.

Generates the sale receipt PDF into a temporary directory, renders a
WYSIWYG preview with QPdfView, and offers print and save actions.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from opticamanager.core.logging_config import get_logger
from opticamanager.services.pdf_service import (
    generate_sale_receipt,
    render_sale_receipt,
    suggest_sale_receipt_path,
)
from opticamanager.ui.widgets.dialogs import dialogo_error, dialogo_informacion

log = get_logger(__name__)


class ReceiptDialog(QDialog):
    """Modal preview of a sale invoice with print and save actions."""

    def __init__(
        self,
        sale_id: int,
        parent: QWidget | None = None,
        lineas: list[str] | None = None,
        titulo: str = "Factura",
    ) -> None:
        super().__init__(parent)
        self._sale_id = sale_id
        self._tmp_dir = tempfile.TemporaryDirectory(prefix="factura_")
        self._pdf_doc: QPdfDocument | None = None

        self.setWindowTitle(titulo)
        self.resize(760, 640)

        layout = QVBoxLayout(self)

        self._summary = QLabel("\n".join(lineas or []))
        self._summary.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._summary)

        self._preview = QPdfView(self)
        self._preview.setPageMode(QPdfView.PageMode.SinglePage)
        self._preview.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        layout.addWidget(self._preview, 1)

        self._fallback = QLabel("Vista previa no disponible")
        self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback.hide()
        layout.addWidget(self._fallback, 1)

        botones = QHBoxLayout()
        self.btn_imprimir = QPushButton("Imprimir")
        self.btn_guardar = QPushButton("Guardar PDF")
        self.btn_cerrar = QPushButton("Cerrar")
        self.btn_imprimir.clicked.connect(self.imprimir)
        self.btn_guardar.clicked.connect(self.guardar_pdf)
        self.btn_cerrar.clicked.connect(self.reject)
        botones.addWidget(self.btn_imprimir)
        botones.addWidget(self.btn_guardar)
        botones.addStretch(1)
        botones.addWidget(self.btn_cerrar)
        layout.addLayout(botones)

        self._cargar_preview()

    def _cargar_preview(self) -> None:
        """Render the receipt PDF into the temporary dir and show it."""
        try:
            pdf_path = Path(self._tmp_dir.name) / "factura.pdf"
            generate_sale_receipt(self._sale_id, pdf_path)
        except Exception as e:  # noqa: BLE001 - preview must degrade gracefully
            log.warning("No se pudo generar la vista previa: %s", e)
            self._preview.hide()
            self._fallback.show()
            return

        doc = QPdfDocument(None)
        if doc.load(str(pdf_path)) != QPdfDocument.Error.None_:
            log.warning("No se pudo cargar la vista previa del recibo")
            doc.close()
            self._preview.hide()
            self._fallback.show()
            return

        self._pdf_doc = doc
        self._preview.setDocument(doc)

    def imprimir(self) -> None:
        """Open the system print dialog and paint the receipt to the printer."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialogo = QPrintDialog(printer, self)
        dialogo.setWindowTitle("Imprimir factura")
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            render_sale_receipt(printer, self._sale_id)
            log.info("recibo_impreso: sale_id=%d", self._sale_id)
        except Exception as e:  # noqa: BLE001 - surface the failure to the user
            log.error("No se pudo imprimir el recibo: %s", e)
            dialogo_error(self, "Error", "No se pudo imprimir el recibo", str(e))

    def guardar_pdf(self) -> None:
        """Ask for a destination and write the receipt PDF to disk."""
        try:
            default_path = suggest_sale_receipt_path(self._sale_id)
        except Exception as e:  # noqa: BLE001 - surface the failure to the user
            log.error("Error al preparar el recibo PDF: %s", e)
            dialogo_error(self, "Error", "No se pudo preparar el recibo PDF", str(e))
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar recibo PDF", str(default_path), "PDF (*.pdf)"
        )
        if not path:
            return
        try:
            generate_sale_receipt(self._sale_id, path)
            dialogo_informacion(self, "Recibo generado", f"Recibo guardado en:\n{path}")
        except Exception as e:  # noqa: BLE001 - surface the failure to the user
            log.error("Error al generar recibo PDF: %s", e)
            dialogo_error(self, "Error", "No se pudo generar el recibo PDF", str(e))

    def _cleanup(self) -> None:
        """Close the document and remove the temporary directory."""
        if self._pdf_doc is not None:
            self._pdf_doc.close()
            self._pdf_doc = None
        self._tmp_dir.cleanup()

    def done(self, result: int) -> None:
        """Release PDF resources before the dialog closes."""
        self._cleanup()
        super().done(result)


def show_sale_receipt(
    parent: QWidget | None,
    sale_id: int,
    lineas: list[str] | None = None,
    titulo: str = "Factura",
) -> None:
    """Open the receipt dialog modally for an existing sale."""
    dialogo = ReceiptDialog(sale_id, parent, lineas=lineas, titulo=titulo)
    dialogo.exec()
