"""Customer management (ClientesView) with full CRUD.

Side view that lists, creates, edits and deletes customers, and opens the
prescriptions of the selected customer (see recetas_view.py).
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sqlalchemy import func
from sqlmodel import select

from opticamanager.core.logging_config import get_logger
from opticamanager.db import SessionManager
from opticamanager.models import Customer, Prescription, Sale
from opticamanager.ui.views.recetas_view import RecetasDialog
from opticamanager.ui.widgets.dialogs import dialogo_confirmacion, dialogo_error
from opticamanager.ui.widgets.table_widget import TablaPersonalizada
from opticamanager.ui.widgets.validators import validador_cedula, validador_telefono

log = get_logger(__name__)

__all__ = ["ClientesView", "CustomerDialog"]


class CustomerDialog(QDialog):
    """Form to create or edit a customer."""

    def __init__(
        self,
        parent: QWidget | None = None,
        customer: Customer | None = None,
    ) -> None:
        super().__init__(parent)
        self._customer = customer
        self.setWindowTitle("Editar Cliente" if customer else "Nuevo Cliente")
        self.setMinimumWidth(420)
        self._setup_ui()
        if customer:
            self._fill_form(customer)

    def _setup_ui(self) -> None:
        form = QFormLayout()

        self._doc = QLineEdit()
        self._doc.setMaxLength(20)
        self._doc.setValidator(validador_cedula())
        form.addRow("Cédula:", self._doc)

        self._name = QLineEdit()
        self._name.setMaxLength(150)
        form.addRow("Nombre:", self._name)

        self._phone = QLineEdit()
        self._phone.setMaxLength(20)
        self._phone.setValidator(validador_telefono())
        form.addRow("Teléfono:", self._phone)

        self._email = QLineEdit()
        self._email.setMaxLength(100)
        form.addRow("Email:", self._email)

        self._address = QLineEdit()
        form.addRow("Dirección:", self._address)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _fill_form(self, c: Customer) -> None:
        self._doc.setText(c.id_document)
        self._name.setText(c.name)
        if c.phone:
            self._phone.setText(c.phone)
        if c.email:
            self._email.setText(c.email)
        if c.address:
            self._address.setText(c.address)

    def _validate_and_accept(self) -> None:
        if not self._doc.text().strip():
            QMessageBox.warning(self, "Validación", "La cédula es obligatoria")
            return
        if not self._name.text().strip():
            QMessageBox.warning(self, "Validación", "El nombre es obligatorio")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "id_document": self._doc.text().strip(),
            "name": self._name.text().strip(),
            "phone": self._phone.text().strip() or None,
            "email": self._email.text().strip() or None,
            "address": self._address.text().strip() or None,
        }


class ClientesView(QWidget):
    """Customer management view."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._load_data()

    def _setup_ui(self) -> None:
        title = QLabel("👥 Clientes")
        title.setObjectName("title-h1")

        btn_nuevo = QPushButton("+ Nuevo Cliente")
        btn_nuevo.setProperty("success", True)
        btn_nuevo.clicked.connect(self._nuevo_cliente)

        self._btn_editar = QPushButton("Editar")
        self._btn_editar.clicked.connect(self._editar_cliente)

        self._btn_eliminar = QPushButton("Eliminar")
        self._btn_eliminar.setProperty("danger", True)
        self._btn_eliminar.clicked.connect(self._eliminar_cliente)

        btn_recetas = QPushButton("📋 Ver Recetas")
        btn_recetas.clicked.connect(self._ver_recetas)

        toolbar = QHBoxLayout()
        toolbar.addWidget(btn_nuevo)
        toolbar.addWidget(self._btn_editar)
        toolbar.addWidget(self._btn_eliminar)
        toolbar.addWidget(btn_recetas)
        toolbar.addStretch()

        self._tabla = TablaPersonalizada()
        self._tabla.set_columns(
            [
                "ID",
                "Cédula",
                "Nombre",
                "Teléfono",
                "Email",
                "Dirección",
                "Recetas",
            ]
        )
        self._tabla.view().setColumnHidden(0, True)

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.addWidget(title)
        layout.addLayout(toolbar)
        layout.addWidget(self._tabla)
        self.setLayout(layout)

    # ── Data ──────────────────────────────────

    def _receta_counts(self, session) -> dict[int, int]:
        """Return a map customer_id -> number of prescriptions."""
        rows = session.exec(
            select(Prescription.customer_id, func.count(Prescription.id)).group_by(
                Prescription.customer_id
            )
        ).all()
        return dict(rows)

    def _load_data(self) -> None:
        self._tabla.clear()
        with SessionManager() as session:
            customers = session.exec(select(Customer).order_by(Customer.name)).all()
            counts = self._receta_counts(session)
        for c in customers:
            self._tabla.add_row(
                [
                    str(c.id),
                    c.id_document,
                    c.name,
                    c.phone or "—",
                    c.email or "—",
                    c.address or "—",
                    str(counts.get(c.id, 0)),
                ]
            )

    def _selected_customer_id(self) -> int | None:
        row = self._tabla.view().currentIndex().row()
        if row < 0:
            return None
        proxy = self._tabla.proxy()
        source_idx = proxy.mapToSource(proxy.index(row, 0))
        model = self._tabla.model()
        item = model.item(source_idx.row(), 0)
        if not item:
            return None
        try:
            return int(item.text())
        except ValueError:
            return None

    # ── Actions ──────────────────────────────

    def _nuevo_cliente(self) -> None:
        dlg = CustomerDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        try:
            with SessionManager() as session:
                c = Customer(**data)
                session.add(c)
                session.commit()
            self._load_data()
        except Exception as e:
            log.error("Error al crear cliente: %s", e)
            dialogo_error(self, "Error", "No se pudo crear el cliente", str(e))

    def _editar_cliente(self) -> None:
        customer_id = self._selected_customer_id()
        if customer_id is None:
            QMessageBox.information(self, "Editar", "Seleccione un cliente")
            return
        with SessionManager() as session:
            c = session.get(Customer, customer_id)
            if not c:
                return
            dlg = CustomerDialog(self, c)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            data = dlg.get_data()
            for key, val in data.items():
                setattr(c, key, val)
            session.add(c)
            session.commit()
        self._load_data()

    def _eliminar_cliente(self) -> None:
        customer_id = self._selected_customer_id()
        if customer_id is None:
            QMessageBox.information(self, "Eliminar", "Seleccione un cliente")
            return

        with SessionManager() as session:
            c = session.get(Customer, customer_id)
            if not c:
                return
            rx_count = session.exec(
                select(func.count())
                .select_from(Prescription)
                .where(Prescription.customer_id == customer_id)
            ).one()
            sale_count = session.exec(
                select(func.count())
                .select_from(Sale)
                .where(Sale.customer_id == customer_id)
            ).one()
            name = c.name

        if rx_count > 0 or sale_count > 0:
            QMessageBox.information(
                self,
                "No se puede eliminar",
                f"'{name}' tiene recetas o ventas asociadas.\n"
                "Elimine primero ese historial para continuar.",
            )
            return

        if not dialogo_confirmacion(
            self,
            "Eliminar Cliente",
            f"¿Eliminar '{name}'?",
        ):
            return

        try:
            with SessionManager() as session:
                c = session.get(Customer, customer_id)
                if c:
                    session.delete(c)
                    session.commit()
            self._load_data()
        except Exception as e:
            log.error("Error al eliminar cliente: %s", e)
            dialogo_error(self, "Error", "No se pudo eliminar el cliente", str(e))

    def _ver_recetas(self) -> None:
        customer_id = self._selected_customer_id()
        if customer_id is None:
            QMessageBox.information(self, "Recetas", "Seleccione un cliente")
            return
        with SessionManager() as session:
            c = session.get(Customer, customer_id)
            if not c:
                return
            dlg = RecetasDialog(c, self)
            dlg.exec()
