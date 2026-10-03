"""Prescription management for a customer.

Covers the prescription create/edit form (OD/OI data, DP, date and notes) and
a per-customer management dialog, reusable from the customer view and from the
POS.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from sqlmodel import select

from opticamanager.core.logging_config import get_logger
from opticamanager.db import SessionManager
from opticamanager.models import Customer, Prescription
from opticamanager.ui.widgets.dialogs import dialogo_confirmacion, dialogo_error
from opticamanager.ui.widgets.table_widget import TablaPersonalizada

log = get_logger(__name__)

__all__ = ["RecetasDialog", "PrescriptionFormDialog"]


def _fmt_opt(value: Decimal | None, unit: str = "") -> str:
    """Format an optional decimal value with 2 decimals and optional unit."""
    if value is None:
        return ""
    return f"{value:,.2f}{unit}"


class PrescriptionFormDialog(QDialog):
    """Form to create or edit a prescription (OD/OI data, DP, notes)."""

    def __init__(
        self,
        parent: QWidget | None = None,
        customer: Customer | None = None,
        prescription: Prescription | None = None,
    ) -> None:
        super().__init__(parent)
        self._customer = customer
        self._prescription = prescription
        self.setWindowTitle("Editar Receta" if prescription else "Nueva Receta")
        self.setMinimumWidth(460)
        self._setup_ui()
        if prescription:
            self._fill_form(prescription)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        if self._customer:
            header = QLabel(
                f"<b>Cliente:</b> {self._customer.name} ({self._customer.id_document})"
            )
            layout.addWidget(header)

        form = QFormLayout()

        # ── OD (right eye) ──
        self._od_sphere = QDoubleSpinBox()
        self._setup_spin(self._od_sphere, 0.25, -20.00, 20.00)
        form.addRow("OD Esfera:", self._od_sphere)

        self._od_cylinder = QDoubleSpinBox()
        self._setup_spin(self._od_cylinder, 0.25, -20.00, 20.00)
        form.addRow("OD Cilindro:", self._od_cylinder)

        self._od_axis = QSpinBox()
        self._setup_axis(self._od_axis)
        form.addRow("OD Eje:", self._od_axis)

        self._od_addition = QDoubleSpinBox()
        self._setup_spin(self._od_addition, 0.25, -20.00, 20.00)
        form.addRow("OD Adición:", self._od_addition)

        # ── OI (left eye) ──
        self._os_sphere = QDoubleSpinBox()
        self._setup_spin(self._os_sphere, 0.25, -20.00, 20.00)
        form.addRow("OI Esfera:", self._os_sphere)

        self._os_cylinder = QDoubleSpinBox()
        self._setup_spin(self._os_cylinder, 0.25, -20.00, 20.00)
        form.addRow("OI Cilindro:", self._os_cylinder)

        self._os_axis = QSpinBox()
        self._setup_axis(self._os_axis)
        form.addRow("OI Eje:", self._os_axis)

        self._os_addition = QDoubleSpinBox()
        self._setup_spin(self._os_addition, 0.25, -20.00, 20.00)
        form.addRow("OI Adición:", self._os_addition)

        # ── DP / date / notes ──
        self._pupillary_distance = QDoubleSpinBox()
        self._setup_spin(self._pupillary_distance, 0.5, 40.00, 90.00)
        form.addRow("DP (mm):", self._pupillary_distance)

        self._issued_date = QDateEdit()
        self._issued_date.setCalendarPopup(True)
        self._issued_date.setDate(QDate.currentDate())
        self._issued_date.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Fecha:", self._issued_date)

        self._notes = QTextEdit()
        self._notes.setPlaceholderText("Notas u observaciones (opcional)")
        self._notes.setFixedHeight(80)
        form.addRow("Notas:", self._notes)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    @staticmethod
    def _setup_spin(
        spin: QDoubleSpinBox, step: float, mini: float, maxi: float
    ) -> None:
        spin.setDecimals(2)
        spin.setRange(mini, maxi)
        spin.setSingleStep(step)
        spin.setValue(0.00)

    @staticmethod
    def _setup_axis(spin: QSpinBox) -> None:
        spin.setRange(0, 180)
        spin.setSingleStep(1)
        spin.setValue(0)

    def _fill_form(self, rx: Prescription) -> None:
        def _set_opt(spin: QDoubleSpinBox, value: Decimal | None) -> None:
            if value is not None:
                spin.setValue(float(value))

        _set_opt(self._od_sphere, rx.od_sphere)
        _set_opt(self._od_cylinder, rx.od_cylinder)
        self._od_axis.setValue(rx.od_axis or 0)
        _set_opt(self._od_addition, rx.od_addition)
        _set_opt(self._os_sphere, rx.os_sphere)
        _set_opt(self._os_cylinder, rx.os_cylinder)
        self._os_axis.setValue(rx.os_axis or 0)
        _set_opt(self._os_addition, rx.os_addition)
        if rx.pupillary_distance is not None:
            self._pupillary_distance.setValue(float(rx.pupillary_distance))
        self._issued_date.setDate(
            QDate(rx.issued_date.year, rx.issued_date.month, rx.issued_date.day)
        )
        if rx.notes:
            self._notes.setPlainText(rx.notes)

    def get_data(self) -> dict:
        def _opt(value: float) -> Decimal | None:
            return None if value == 0.00 else Decimal(str(value))

        issued = self._issued_date.date()
        return {
            "customer_id": self._customer.id if self._customer else None,
            "od_sphere": _opt(self._od_sphere.value()),
            "od_cylinder": _opt(self._od_cylinder.value()),
            "od_axis": self._od_axis.value() or None,
            "od_addition": _opt(self._od_addition.value()),
            "os_sphere": _opt(self._os_sphere.value()),
            "os_cylinder": _opt(self._os_cylinder.value()),
            "os_axis": self._os_axis.value() or None,
            "os_addition": _opt(self._os_addition.value()),
            "pupillary_distance": _opt(self._pupillary_distance.value()),
            "issued_date": date(issued.year(), issued.month(), issued.day()),
            "notes": self._notes.toPlainText().strip() or None,
        }


class RecetasDialog(QDialog):
    """Manage a customer's prescriptions: list, create, edit, delete.

    An optional 'pick mode' (set_pick_mode) lets the POS choose a prescription
    to attach to a sale.
    """

    def __init__(
        self,
        customer: Customer,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._customer = customer
        self._selected_prescription: Prescription | None = None
        self.setWindowTitle(f"Recetas — {customer.name}")
        self.setMinimumSize(720, 460)
        self._setup_ui()
        self._load_data()

    @property
    def selected_prescription(self) -> Prescription | None:
        return self._selected_prescription

    def set_pick_mode(self) -> None:
        """Show the 'Usar receta' button so the dialog returns a selection."""
        self._btn_use.setVisible(True)

    # ── UI ────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        header = QLabel(
            f"<b>Cliente:</b> {self._customer.name} ({self._customer.id_document})"
        )
        header.setObjectName("rx-header")
        layout.addWidget(header)

        self._tabla = TablaPersonalizada()
        self._tabla.set_columns(
            [
                "ID",
                "Fecha",
                "OD Esf",
                "OD Cil",
                "OD Eje",
                "OI Esf",
                "OI Cil",
                "OI Eje",
                "DP",
                "Notas",
            ]
        )
        self._tabla.view().setColumnHidden(0, True)
        self._tabla.view().doubleClicked.connect(self._show_detail)
        layout.addWidget(self._tabla)

        btn_row = QHBoxLayout()

        self._btn_use = QPushButton("Usar receta para esta venta")
        self._btn_use.setVisible(False)
        self._btn_use.setProperty("success", True)
        self._btn_use.clicked.connect(self._accept_selection)
        btn_row.addWidget(self._btn_use)

        btn_new = QPushButton("+ Nueva Receta")
        btn_new.setProperty("success", True)
        btn_new.clicked.connect(self._nueva_receta)
        btn_row.addWidget(btn_new)

        self._btn_edit = QPushButton("Editar")
        self._btn_edit.clicked.connect(self._editar_receta)
        btn_row.addWidget(self._btn_edit)

        self._btn_delete = QPushButton("Eliminar")
        self._btn_delete.setProperty("danger", True)
        self._btn_delete.clicked.connect(self._eliminar_receta)
        btn_row.addWidget(self._btn_delete)

        btn_detail = QPushButton("Ver detalle")
        btn_detail.clicked.connect(self._show_detail)
        btn_row.addWidget(btn_detail)

        btn_print = QPushButton("Imprimir receta")
        btn_print.clicked.connect(self._print_prescription)
        btn_row.addWidget(btn_print)

        btn_row.addStretch()

        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)
        self.setLayout(layout)

    # ── Datos ─────────────────────────────────

    def _load_data(self) -> None:
        self._tabla.clear()
        with SessionManager() as session:
            stmt = (
                select(Prescription)
                .where(Prescription.customer_id == self._customer.id)
                .order_by(Prescription.issued_date.desc())
            )
            recetas = session.exec(stmt).all()

        for r in recetas:
            self._tabla.add_row(
                [
                    str(r.id) if r.id else "",
                    r.issued_date.isoformat(),
                    _fmt_opt(r.od_sphere),
                    _fmt_opt(r.od_cylinder),
                    str(r.od_axis or ""),
                    _fmt_opt(r.os_sphere),
                    _fmt_opt(r.os_cylinder),
                    str(r.os_axis or ""),
                    _fmt_opt(r.pupillary_distance, "mm"),
                    (r.notes[:50] + "…")
                    if r.notes and len(r.notes) > 50
                    else (r.notes or ""),
                ]
            )

    def _current_row_id(self) -> int:
        row = self._tabla.view().currentIndex().row()
        if row < 0:
            return 0
        proxy = self._tabla.proxy()
        source_idx = proxy.mapToSource(proxy.index(row, 0))
        model = self._tabla.model()
        item = model.item(source_idx.row(), 0)
        return int(item.text()) if item else 0

    # ── CRUD actions ─────────────────────────

    def _nueva_receta(self) -> None:
        dlg = PrescriptionFormDialog(self, customer=self._customer)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        data["customer_id"] = self._customer.id
        try:
            with SessionManager() as session:
                rx = Prescription(**data)
                session.add(rx)
                session.commit()
            self._load_data()
        except Exception as e:
            log.error("Error al crear receta: %s", e)
            dialogo_error(self, "Error", "No se pudo crear la receta", str(e))

    def _editar_receta(self) -> None:
        rx_id = self._current_row_id()
        if not rx_id:
            self._no_selection("Editar")
            return
        with SessionManager() as session:
            rx = session.get(Prescription, rx_id)
            if not rx:
                return
            dlg = PrescriptionFormDialog(self, prescription=rx)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            data = dlg.get_data()
            data.pop("customer_id", None)  # never change the customer on edit
            for key, val in data.items():
                setattr(rx, key, val)
            session.add(rx)
            session.commit()
        self._load_data()

    def _eliminar_receta(self) -> None:
        rx_id = self._current_row_id()
        if not rx_id:
            self._no_selection("Eliminar")
            return
        if not dialogo_confirmacion(
            self,
            "Eliminar Receta",
            f"¿Eliminar la receta #{rx_id}?",
        ):
            return
        try:
            with SessionManager() as session:
                rx = session.get(Prescription, rx_id)
                if rx:
                    session.delete(rx)
                    session.commit()
            self._load_data()
        except Exception as e:
            log.error("Error al eliminar receta: %s", e)
            dialogo_error(self, "Error", "No se pudo eliminar la receta", str(e))

    def _no_selection(self, action: str) -> None:
        QMessageBox.information(self, action, "Seleccione una receta de la tabla")

    # ── Detail / print / pick ────────────────────────

    def _show_detail(self) -> None:
        rx_id = self._current_row_id()
        if not rx_id:
            self._no_selection("Detalle")
            return

        with SessionManager() as session:
            receta = session.get(Prescription, rx_id)
            if not receta:
                return

        detail = (
            f"<b>Fecha:</b> {receta.issued_date.isoformat()}<br><br>"
            f"<b>Ojo Derecho (OD)</b><br>"
            f"  Esfera: {_fmt_opt(receta.od_sphere)}<br>"
            f"  Cilindro: {_fmt_opt(receta.od_cylinder)}<br>"
            f"  Eje: {receta.od_axis or '—'}<br>"
            f"  Adición: {_fmt_opt(receta.od_addition)}<br><br>"
            f"<b>Ojo Izquierdo (OI)</b><br>"
            f"  Esfera: {_fmt_opt(receta.os_sphere)}<br>"
            f"  Cilindro: {_fmt_opt(receta.os_cylinder)}<br>"
            f"  Eje: {receta.os_axis or '—'}<br>"
            f"  Adición: {_fmt_opt(receta.os_addition)}<br><br>"
            f"<b>DP:</b> {_fmt_opt(receta.pupillary_distance, 'mm')}<br>"
            f"<b>Notas:</b> {receta.notes or '—'}"
        )
        QMessageBox.information(self, f"Receta #{rx_id}", detail)

    def _print_prescription(self) -> None:
        rx_id = self._current_row_id()
        if not rx_id:
            self._no_selection("Imprimir")
            return

        default_name = None
        try:
            from opticamanager.services.pdf_service import suggest_prescription_path

            default_name = suggest_prescription_path(rx_id)
        except Exception as e:
            log.error("Error al preparar la receta PDF: %s", e)
            dialogo_error(self, "Error", "No se pudo preparar la receta PDF", str(e))
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar receta PDF",
            str(default_name),
            "PDF (*.pdf)",
        )
        if not path:
            return
        try:
            from opticamanager.services.pdf_service import generate_prescription

            generate_prescription(rx_id, path)
            QMessageBox.information(
                self,
                "Receta generada",
                f"Receta guardada en:\n{path}",
            )
        except Exception as e:
            log.error("Error al generar receta PDF: %s", e)
            dialogo_error(self, "Error", "No se pudo generar la receta PDF", str(e))

    def _accept_selection(self) -> None:
        rx_id = self._current_row_id()
        if not rx_id:
            QMessageBox.information(
                self, "Seleccionar", "Seleccione una receta de la tabla"
            )
            return
        with SessionManager() as session:
            self._selected_prescription = session.get(Prescription, rx_id)
        self.accept()
