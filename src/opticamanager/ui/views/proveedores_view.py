from __future__ import annotations

from decimal import Decimal

from PyQt6.QtGui import QStandardItemModel
from PyQt6.QtWidgets import (
    QComboBox,
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

from sqlmodel import select

from opticamanager.db import SessionManager
from opticamanager.models import Supplier
from opticamanager.ui.widgets.dialogs import dialogo_confirmacion, dialogo_error
from opticamanager.ui.widgets.table_widget import TablaPersonalizada
from opticamanager.ui.widgets.validators import validador_moneda, validador_telefono


class _SupplierDialog(QDialog):
    def __init__(
        self, parent: QWidget | None = None, supplier: Supplier | None = None
    ) -> None:
        super().__init__(parent)
        self._supplier = supplier
        self.setWindowTitle("Editar Proveedor" if supplier else "Nuevo Proveedor")
        self.setMinimumWidth(450)
        self._setup_ui()
        if supplier:
            self._fill_form(supplier)

    def _setup_ui(self) -> None:
        form = QFormLayout()

        self._company = QLineEdit()
        self._company.setMaxLength(150)
        form.addRow("Empresa:", self._company)

        self._contact = QLineEdit()
        self._contact.setMaxLength(100)
        form.addRow("Contacto:", self._contact)

        self._phone = QLineEdit()
        self._phone.setMaxLength(20)
        self._phone.setValidator(validador_telefono())
        form.addRow("Teléfono:", self._phone)

        self._email = QLineEdit()
        self._email.setMaxLength(100)
        form.addRow("Email:", self._email)

        self._address = QLineEdit()
        form.addRow("Dirección:", self._address)

        self._debt = QLineEdit()
        self._debt.setValidator(validador_moneda())
        self._debt.setText("0.00")
        form.addRow("Deuda actual (Bs.):", self._debt)

        self._active = QComboBox()
        self._active.addItem("Sí", True)
        self._active.addItem("No", False)
        form.addRow("Activo:", self._active)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _fill_form(self, s: Supplier) -> None:
        self._company.setText(s.company_name)
        if s.contact_name:
            self._contact.setText(s.contact_name)
        if s.phone:
            self._phone.setText(s.phone)
        if s.email:
            self._email.setText(s.email)
        if s.address:
            self._address.setText(s.address)
        self._debt.setText(str(s.current_debt))
        self._active.setCurrentIndex(0 if s.active else 1)

    def _validate_and_accept(self) -> None:
        if not self._company.text().strip():
            QMessageBox.warning(
                self, "Validación", "El nombre de empresa es obligatorio"
            )
            return
        if not self._phone.text().strip():
            QMessageBox.warning(self, "Validación", "El teléfono es obligatorio")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "company_name": self._company.text().strip(),
            "contact_name": self._contact.text().strip() or None,
            "phone": self._phone.text().strip(),
            "email": self._email.text().strip() or None,
            "address": self._address.text().strip() or None,
            "current_debt": Decimal(self._debt.text() or "0"),
            "active": self._active.currentData(),
        }


class _PagoDeudaDialog(QDialog):
    def __init__(self, parent: QWidget | None, supplier: Supplier) -> None:
        super().__init__(parent)
        self._supplier = supplier
        self.setWindowTitle(f"Pagar deuda — {supplier.company_name}")
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        info = QLabel(
            f"<b>Proveedor:</b> {self._supplier.company_name}<br>"
            f"<b>Deuda actual:</b> Bs. {self._supplier.current_debt:,.2f}"
        )
        info.setWordWrap(True)
        info.setObjectName("supplier-info")
        layout.addWidget(info)

        form = QFormLayout()
        self._monto = QLineEdit()
        self._monto.setValidator(validador_moneda())
        self._monto.setText(str(self._supplier.current_debt))
        form.addRow("Monto a pagar (Bs.):", self._monto)

        self._restante = QLabel("Deuda restante: Bs. 0.00")
        self._restante.setObjectName("debt-remaining")
        form.addRow("", self._restante)
        self._monto.textChanged.connect(self._actualizar_restante)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Pagar")  # type: ignore[union-attr]  # button() may return None per stub, guaranteed present
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)
        self._actualizar_restante()

    def _actualizar_restante(self) -> None:
        try:
            monto = Decimal(self._monto.text() or "0")
        except Exception:
            monto = Decimal("0")
        restante = max(Decimal("0"), self._supplier.current_debt - monto)
        self._restante.setText(f"Deuda restante: Bs. {restante:,.2f}")

    def _validate_and_accept(self) -> None:
        try:
            monto = Decimal(self._monto.text() or "0")
        except Exception:
            monto = Decimal("0")
        if monto <= 0:
            QMessageBox.warning(self, "Validación", "El monto debe ser mayor a cero")
            return
        if monto > self._supplier.current_debt:
            QMessageBox.warning(
                self,
                "Validación",
                f"El monto supera la deuda actual (Bs. {self._supplier.current_debt:,.2f})",
            )
            return
        self.accept()

    def monto_pago(self) -> Decimal:
        return Decimal(self._monto.text() or "0")


class ProveedoresView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._setup_ui()
        self._load_data()

    @staticmethod
    def _get_selected_id(model: QStandardItemModel, row: int) -> int:
        item = model.item(row, 0)
        return int(item.text()) if item else 0

    @staticmethod
    def _get_selected_name(model: QStandardItemModel, row: int) -> str:
        item = model.item(row, 1)
        return item.text() if item else ""

    def _selected_row(self) -> int | None:
        row = self._tabla.view().currentIndex().row()
        if row < 0:
            QMessageBox.information(
                self, "Seleccionar", "Seleccione un proveedor de la tabla"
            )
            return None
        return row

    def _selected_supplier_id(self) -> int | None:
        row = self._selected_row()
        if row is None:
            return None
        proxy = self._tabla.proxy()
        source_idx = proxy.mapToSource(proxy.index(row, 0))
        return self._get_selected_id(self._tabla.model(), source_idx.row())

    def _setup_ui(self) -> None:
        title = QLabel("Proveedores")
        title.setObjectName("title-h2")

        btn_nuevo = QPushButton("+ Nuevo Proveedor")
        btn_nuevo.setProperty("success", True)
        btn_nuevo.clicked.connect(self._nuevo_proveedor)

        self._btn_editar = QPushButton("Editar")
        self._btn_editar.clicked.connect(self._editar_proveedor)

        self._btn_eliminar = QPushButton("Eliminar")
        self._btn_eliminar.setProperty("danger", True)
        self._btn_eliminar.clicked.connect(self._eliminar_proveedor)

        btn_pagar = QPushButton("💰 Pagar Deuda")
        btn_pagar.setProperty("success", True)
        btn_pagar.clicked.connect(self._pagar_deuda)

        toolbar = QHBoxLayout()
        toolbar.addWidget(btn_nuevo)
        toolbar.addWidget(self._btn_editar)
        toolbar.addWidget(self._btn_eliminar)
        toolbar.addWidget(btn_pagar)
        toolbar.addStretch()

        self._tabla = TablaPersonalizada()
        self._tabla.set_columns(
            ["ID", "Empresa", "Contacto", "Teléfono", "Email", "Deuda (Bs.)", "Estado"]
        )
        self._tabla.view().setColumnHidden(0, True)

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.addWidget(title)
        layout.addLayout(toolbar)
        layout.addWidget(self._tabla)
        self.setLayout(layout)

    def _load_data(self) -> None:
        self._tabla.clear()
        with SessionManager() as session:
            suppliers = session.exec(
                select(Supplier).order_by(Supplier.company_name)
            ).all()
        for s in suppliers:
            self._tabla.add_row(
                [
                    str(s.id),
                    s.company_name,
                    s.contact_name or "—",
                    s.phone or "—",
                    s.email or "—",
                    f"Bs. {s.current_debt:,.2f}",
                    "Activo" if s.active else "Inactivo",
                ]
            )

    def _nuevo_proveedor(self) -> None:
        dlg = _SupplierDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        try:
            with SessionManager() as session:
                s = Supplier(**data)
                session.add(s)
                session.commit()
            self._load_data()
        except Exception as e:
            dialogo_error(self, "Error", "No se pudo crear el proveedor", str(e))

    def _editar_proveedor(self) -> None:
        supplier_id = self._selected_supplier_id()
        if supplier_id is None:
            return
        with SessionManager() as session:
            s = session.get(Supplier, supplier_id)
            if not s:
                return
            dlg = _SupplierDialog(self, s)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            data = dlg.get_data()
            for key, val in data.items():
                setattr(s, key, val)
            session.add(s)
            session.commit()
        self._load_data()

    def _eliminar_proveedor(self) -> None:
        supplier_id = self._selected_supplier_id()
        if supplier_id is None:
            return
        row = self._tabla.view().currentIndex().row()
        proxy = self._tabla.proxy()
        source_idx = proxy.mapToSource(proxy.index(row, 0))
        name = self._get_selected_name(self._tabla.model(), source_idx.row())
        if not dialogo_confirmacion(
            self,
            "Eliminar Proveedor",
            f"¿Eliminar '{name}'?",
        ):
            return
        try:
            with SessionManager() as session:
                s = session.get(Supplier, supplier_id)
                if s:
                    session.delete(s)
                    session.commit()
            self._load_data()
        except Exception as e:
            dialogo_error(self, "Error", "No se pudo eliminar el proveedor", str(e))

    def _pagar_deuda(self) -> None:
        supplier_id = self._selected_supplier_id()
        if supplier_id is None:
            return
        with SessionManager() as session:
            s = session.get(Supplier, supplier_id)
            if not s:
                return
            if s.current_debt <= 0:
                QMessageBox.information(
                    self,
                    "Sin deuda",
                    f"{s.company_name} no tiene deuda pendiente",
                )
                return
            dlg = _PagoDeudaDialog(self, s)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            monto = dlg.monto_pago()
            s.current_debt -= monto
            session.add(s)
            session.commit()
            QMessageBox.information(
                self,
                "Pago registrado",
                f"Pago de Bs. {monto:,.2f} registrado.\n"
                f"Deuda restante: Bs. {s.current_debt:,.2f}",
            )
        self._load_data()
