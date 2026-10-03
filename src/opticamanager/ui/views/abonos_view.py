"""Abonos view: pending sales and partial payments."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlmodel import col, func, select

from opticamanager.core.logging_config import get_logger
from opticamanager.db import SessionManager
from opticamanager.models.customer import Customer
from opticamanager.models.sale import Sale
from opticamanager.models.sale_payment import SalePayment
from opticamanager.services.exchange_rate import get_rate_info
from opticamanager.utils.formatters import format_bs

log = get_logger(__name__)

# Payment methods allowed for abonos (same as POS, minus "Mixto" and "Abono")
PAYMENT_METHODS = ["Pago Móvil", "Zelle", "Efectivo Bs", "Efectivo Dólares"]


class _AbonoDialog(QDialog):
    """Dialog to record a partial payment on a pending sale."""

    def __init__(self, sale: Sale, pendiente: Decimal, parent: QWidget | None = None):
        super().__init__(parent)
        self._sale = sale
        self._pendiente = pendiente
        self._monto: Decimal = Decimal("0")
        self._metodo: str = "Efectivo Bs"
        self.setWindowTitle(f"Abono — {sale.invoice_number}")
        self.setMinimumWidth(420)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()

        info = QLabel(
            f"<b>Factura:</b> {self._sale.invoice_number}<br>"
            f"<b>Total:</b> {format_bs(self._sale.total)}<br>"
            f"<b>Ya pagado:</b> {format_bs(self._sale.total - self._pendiente)}<br>"
            f"<b>Pendiente:</b> <b>{format_bs(self._pendiente)}</b>"
        )
        info.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(info)

        form = QFormLayout()

        self._metodo_combo = QComboBox()
        self._metodo_combo.addItems(PAYMENT_METHODS)
        form.addRow("Método de pago:", self._metodo_combo)

        self._monto_spin = QDoubleSpinBox()
        self._monto_spin.setRange(0.01, float(self._pendiente))
        self._monto_spin.setDecimals(2)
        self._monto_spin.setPrefix("Bs. ")
        self._monto_spin.setValue(float(self._pendiente))
        form.addRow("Monto a abonar:", self._monto_spin)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def _validate_and_accept(self) -> None:
        monto = Decimal(str(self._monto_spin.value()))
        if monto <= 0:
            QMessageBox.warning(
                self, "Monto inválido", "El monto debe ser mayor a cero."
            )
            return
        if monto > self._pendiente:
            QMessageBox.warning(
                self,
                "Monto excesivo",
                f"El monto ({format_bs(monto)}) excede "
                f"el saldo pendiente ({format_bs(self._pendiente)}).",
            )
            return
        self._monto = monto
        self._metodo = self._metodo_combo.currentText()
        self.accept()

    @property
    def monto(self) -> Decimal:
        return self._monto

    @property
    def metodo(self) -> str:
        return self._metodo


class AbonosView(QWidget):
    """Abonos view: pending sales and partial payment records."""

    def __init__(self) -> None:
        super().__init__()
        self._setup_ui()
        self._load_pendientes()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)

        # Header
        header = QHBoxLayout()
        title = QLabel("Abonos pendientes")
        title.setObjectName("title-h1")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        # Search bar
        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Buscar por nombre de cliente...")
        self._search_input.textChanged.connect(self._load_pendientes)
        search_row.addWidget(self._search_input, stretch=1)
        btn_refresh = QPushButton("🔄 Actualizar")
        btn_refresh.clicked.connect(self._load_pendientes)
        search_row.addWidget(btn_refresh)
        layout.addLayout(search_row)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["Cliente", "Factura", "Fecha", "Total", "Pagado", "Pendiente", ""]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeMode.Fixed
        )
        self._table.setColumnWidth(6, 100)
        self._table.verticalHeader().hide()
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        layout.addWidget(self._table, stretch=1)

        # Summary
        self._summary_label = QLabel("")
        self._summary_label.setObjectName("filter-label")
        layout.addWidget(self._summary_label)

        self.setLayout(layout)

    def _load_pendientes(self) -> None:
        """Load all pending sales with remaining balance."""
        search = self._search_input.text().strip().lower()

        with SessionManager() as session:
            stmt = (
                select(Sale, Customer.name.label("customer_name"))  # type: ignore[arg-type]
                .join(Customer, Sale.customer_id == Customer.id)
                .where(Sale.status_id == 2)  # Pendiente
                .order_by(col(Sale.created_at).desc())
            )
            rows = session.exec(stmt).all()

            # Compute payments per sale
            payment_totals: dict[int, Decimal] = {}
            for sale_obj, _ in rows:
                if sale_obj.id not in payment_totals:
                    payment_totals[sale_obj.id] = Decimal("0")
                pay_stmt = select(
                    func.coalesce(func.sum(SalePayment.amount_bs), 0)
                ).where(SalePayment.sale_id == sale_obj.id)
                paid = Decimal(str(session.execute(pay_stmt).scalar_one() or 0))
                payment_totals[sale_obj.id] = paid

        # Filter by search
        filtered = [
            (sale_obj, cname)
            for sale_obj, cname in rows
            if not search or search in cname.lower()
        ]

        self._table.setRowCount(len(filtered))
        total_pendiente = Decimal("0")

        for i, (sale_obj, cname) in enumerate(filtered):
            assert sale_obj.id is not None
            paid = payment_totals.get(sale_obj.id, Decimal("0"))
            pendiente = sale_obj.total - paid
            if pendiente < Decimal("0"):
                pendiente = Decimal("0")
            total_pendiente += pendiente

            # Customer name
            name_item = QTableWidgetItem(cname)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(i, 0, name_item)

            # Invoice number
            inv_item = QTableWidgetItem(sale_obj.invoice_number)
            inv_item.setFlags(inv_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(i, 1, inv_item)

            # Date
            date_str = (
                sale_obj.created_at.strftime("%d/%m/%Y") if sale_obj.created_at else "—"
            )
            date_item = QTableWidgetItem(date_str)
            date_item.setFlags(date_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(i, 2, date_item)

            # Total
            total_item = QTableWidgetItem(format_bs(sale_obj.total))
            total_item.setFlags(total_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            total_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._table.setItem(i, 3, total_item)

            # Paid
            paid_item = QTableWidgetItem(format_bs(paid))
            paid_item.setFlags(paid_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            paid_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._table.setItem(i, 4, paid_item)

            # Pending
            pend_item = QTableWidgetItem(format_bs(pendiente))
            pend_item.setFlags(pend_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            pend_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._table.setItem(i, 5, pend_item)

            # Abonar button
            btn = QPushButton("Abonar")
            btn.setProperty("success", True)
            btn.clicked.connect(
                lambda checked, s=sale_obj, p=pendiente: self._abonar(s, p)
            )
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
            self._table.setCellWidget(i, 6, btn_widget)

        self._summary_label.setText(
            f"Ventas pendientes: {len(filtered)}  |  "
            f"Total por cobrar: {format_bs(total_pendiente)}"
        )

    def _abonar(self, sale: Sale, pendiente: Decimal) -> None:
        """Open dialog to record a partial payment."""
        dlg = _AbonoDialog(sale, pendiente, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        from opticamanager.core.session import UserSession

        user = UserSession().current_user
        if not user:
            QMessageBox.critical(self, "Error", "No hay sesión activa.")
            return

        rate_info = get_rate_info()
        rate = rate_info.rate

        with SessionManager() as session:
            # Reload sale in this session
            sale_db = session.get(Sale, sale.id)
            if not sale_db:
                QMessageBox.critical(self, "Error", "Venta no encontrada.")
                return

            monto = dlg.monto
            metodo = dlg.metodo

            # Determine currency
            if metodo == "Efectivo Dólares":
                currency = "USD"
                rate_val = rate if rate and rate > 0 else None
                amount_bs = (
                    (monto * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    if rate_val
                    else monto
                )
            else:
                currency = "Bs"
                rate_val = None
                amount_bs = monto

            # Create payment record
            payment = SalePayment(  # type: ignore[reportCallIssue]
                sale_id=sale_db.id,  # type: ignore[arg-type]
                method=metodo,
                currency=currency,
                amount=monto,
                amount_bs=amount_bs,
                rate_used=rate_val,
            )
            session.add(payment)

            # Update sale amount_received
            current_received = sale_db.amount_received or Decimal("0")
            sale_db.amount_received = current_received + amount_bs

            # Check if fully paid → mark as Completada
            total_paid_stmt = select(
                func.coalesce(func.sum(SalePayment.amount_bs), 0)
            ).where(SalePayment.sale_id == sale_db.id)
            total_paid = Decimal(
                str(session.execute(total_paid_stmt).scalar_one() or 0)
            )
            total_paid += amount_bs  # include current payment not yet committed

            if total_paid >= sale_db.total:
                sale_db.status_id = 1  # Completada
                log.info(
                    "venta_completada_por_abono: factura=%s",
                    sale_db.invoice_number,
                )

            session.commit()

            nuevo_pendiente = sale_db.total - total_paid
            if nuevo_pendiente < Decimal("0"):
                nuevo_pendiente = Decimal("0")

            result_msg = (
                f"Abono registrado exitosamente.<br><br>"
                f"<b>Factura:</b> {sale_db.invoice_number}<br>"
                f"<b>Abono:</b> {format_bs(amount_bs)}<br>"
                f"<b>Saldo pendiente:</b> {format_bs(nuevo_pendiente)}"
            )
            if nuevo_pendiente <= Decimal("0"):
                result_msg += "<br><br>✅ Venta completada — saldada."

            QMessageBox.information(self, "Abono registrado", result_msg)

        self._load_pendientes()
