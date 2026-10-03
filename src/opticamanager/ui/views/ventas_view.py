"""Sales view: sales history and refunds (admin only)."""

from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
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
from sqlmodel import col, select

from opticamanager.core.logging_config import get_logger
from opticamanager.db import SessionManager
from opticamanager.models.customer import Customer
from opticamanager.models.sale import Sale
from opticamanager.models.sale_status import SaleStatus
from opticamanager.models.user import User
from opticamanager.services.stock_service import reembolsar_venta
from opticamanager.ui.widgets.dialogs import (
    dialogo_confirmacion,
    dialogo_error,
    dialogo_informacion,
)
from opticamanager.utils.formatters import format_bs

log = get_logger(__name__)


class VentasView(QWidget):
    """Sales history with a full refund option (admin only)."""

    def __init__(self) -> None:
        super().__init__()
        self._setup_ui()
        self._load_ventas()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)

        # Header
        header = QHBoxLayout()
        title = QLabel("Historial de Ventas")
        title.setObjectName("title-h1")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        # Search bar
        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Buscar por factura o cliente...")
        self._search_input.textChanged.connect(self._load_ventas)
        search_row.addWidget(self._search_input, stretch=1)
        btn_refresh = QPushButton("🔄 Actualizar")
        btn_refresh.clicked.connect(self._load_ventas)
        search_row.addWidget(btn_refresh)
        layout.addLayout(search_row)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["Fecha", "Factura", "Cliente", "Vendedor", "Total Bs", "Estado", ""]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeMode.Fixed
        )
        self._table.setColumnWidth(6, 120)
        self._table.verticalHeader().hide()
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        layout.addWidget(self._table, stretch=1)

        # Summary
        self._summary_label = QLabel("")
        self._summary_label.setObjectName("filter-label")
        layout.addWidget(self._summary_label)

        self.setLayout(layout)

    def _load_ventas(self) -> None:
        """Load all sales with customer/vendor/status names."""
        search = self._search_input.text().strip().lower()

        with SessionManager() as session:
            stmt = (
                select(
                    Sale,
                    Customer.name.label("customer_name"),  # type: ignore[arg-type]
                    User.name.label("user_name"),  # type: ignore[arg-type]
                    SaleStatus.name.label("status_name"),  # type: ignore[arg-type]
                )
                .join(Customer, Sale.customer_id == Customer.id)
                .join(User, Sale.user_id == User.id)
                .join(SaleStatus, Sale.status_id == SaleStatus.id)
                .order_by(col(Sale.created_at).desc(), Sale.id.desc())
            )
            rows = session.exec(stmt).all()

        filtered = [
            (sale_obj, cname, uname, sname)
            for sale_obj, cname, uname, sname in rows
            if not search
            or search in (cname or "").lower()
            or search in (sale_obj.invoice_number or "").lower()
        ]

        self._table.setRowCount(len(filtered))
        total_ventas = Decimal("0")

        for i, (sale_obj, cname, uname, sname) in enumerate(filtered):
            assert sale_obj.id is not None
            total_ventas += sale_obj.total or Decimal("0")

            # Date
            date_str = (
                sale_obj.created_at.strftime("%d/%m/%Y") if sale_obj.created_at else "—"
            )
            date_item = QTableWidgetItem(date_str)
            date_item.setFlags(date_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(i, 0, date_item)

            # Invoice number
            inv_item = QTableWidgetItem(sale_obj.invoice_number)
            inv_item.setFlags(inv_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(i, 1, inv_item)

            # Customer name
            name_item = QTableWidgetItem(cname or "—")
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(i, 2, name_item)

            # Vendor name
            user_item = QTableWidgetItem(uname or "—")
            user_item.setFlags(user_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(i, 3, user_item)

            # Total
            total_item = QTableWidgetItem(format_bs(sale_obj.total))
            total_item.setFlags(total_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            total_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._table.setItem(i, 4, total_item)

            # Status
            status_item = QTableWidgetItem(sname or "—")
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(i, 5, status_item)

            # Refund button (not for cancelled/refunded sales)
            if sale_obj.status_id not in (3, 4):
                btn = QPushButton("Rembolsar")
                btn.setProperty("success", True)
                btn.setToolTip("Rembolsar venta completa (solo admin)")
                btn.clicked.connect(lambda checked, s=sale_obj: self._rembolsar(s))
                btn_widget = QWidget()
                btn_layout = QHBoxLayout(btn_widget)
                btn_layout.setContentsMargins(0, 0, 0, 0)
                btn_layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
                self._table.setCellWidget(i, 6, btn_widget)

        self._summary_label.setText(
            f"Ventas: {len(filtered)}  |  Total: {format_bs(total_ventas)}"
        )

    def _rembolsar(self, sale: Sale) -> None:
        """Confirm and refund a sale completely (admin only)."""
        from opticamanager.core.session import UserSession

        # Build the confirmation text with details
        with SessionManager() as session:
            sale_db = session.get(Sale, sale.id)
            if not sale_db:
                QMessageBox.critical(self, "Error", "Venta no encontrada.")
                return

            invoice = sale_db.invoice_number
            total = format_bs(sale_db.total)
            customer_name = sale_db.customer.name if sale_db.customer else "—"

            lines = []
            for d in sale_db.details:
                product_name = (
                    d.product.name if d.product else f"Producto #{d.product_id}"
                )
                lines.append(
                    f"  • {product_name} x{d.quantity} = {format_bs(d.subtotal)}"
                )
            items_text = "\n".join(lines) if lines else "  —"

        msg = (
            f"Factura: {invoice}\n"
            f"Cliente: {customer_name}\n"
            f"Ítems:\n{items_text}\n"
            f"Total: {total}\n\n"
            "¿Confirmar el rembolso completo de esta venta?\n"
            "El stock de los productos será restaurado."
        )
        if not dialogo_confirmacion(self, "Rembolsar venta", msg):
            return

        user = UserSession().current_user
        if not user:
            QMessageBox.critical(self, "Error", "No hay sesión activa.")
            return

        try:
            reembolsar_venta(sale_id=sale.id, user_id=user.id)
        except PermissionError as exc:
            dialogo_error(self, "Permiso denegado", str(exc))
            return
        except ValueError as exc:
            dialogo_error(self, "Error de rembolso", str(exc))
            return

        log.info("rembolso_confirmado: factura=%s", invoice)
        dialogo_informacion(
            self,
            "Venta rembolsada",
            f"La venta {invoice} fue rembolsada.\nEl stock fue restaurado.",
        )
        self._load_ventas()
