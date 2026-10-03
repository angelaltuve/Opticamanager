"""Operational reports: sales by day, by seller, by product, and the IVA ledger."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from pathlib import Path

from PyQt6.QtCore import QDate, Qt, QSortFilterProxyModel, QStringListModel
from PyQt6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sqlalchemy import func, text
from sqlmodel import select

from opticamanager.core.logging_config import get_logger
from opticamanager.db import SessionManager
from opticamanager.models.customer import Customer
from opticamanager.services.exchange_rate import get_usd_rate
from opticamanager.models.product import Product
from opticamanager.models.sale import Sale
from opticamanager.models.sale_detail import SaleDetail
from opticamanager.models.user import User
from opticamanager.services.excel_service import export_report_to_excel
from opticamanager.ui.widgets.table_widget import TablaPersonalizada

log = get_logger(__name__)


def _setup_completer(combo: QComboBox, items: list[str]) -> None:
    """Attach a QCompleter with case-insensitive filtering to an editable combo."""
    model = QStringListModel(items)
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    proxy.setFilterRole(0)  # Qt.DisplayRole

    completer = QCompleter(proxy, combo)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    combo.setCompleter(completer)


REPORT_TYPES = [
    "Ventas por día",
    "Ventas por vendedor",
    "Productos más vendidos",
    "Libro de ventas (IVA)",
    "Estado de ganancias",
    "Consulta personalizada",
]


class ReportesView(QWidget):
    """Operational reports view with a report selector and a results table."""

    def __init__(self) -> None:
        super().__init__()
        self._current_data: list[list[str]] = []
        self._current_headers: list[str] = []
        self._current_summary: str = ""
        self._customer_map: dict[int, str] = {}
        self._product_map: dict[int, str] = {}
        self._setup_ui()
        self._populate_filters()
        self._generate_report()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)

        # ── Title ──
        title = QLabel("Reportes Operativos")
        title.setObjectName("title-h2")
        layout.addWidget(title)

        # ── Controls ──
        controls = QFrame()
        controls.setFrameStyle(QFrame.Shape.StyledPanel)
        controls.setObjectName("report-controls")
        controls_layout = QGridLayout(controls)
        controls_layout.setContentsMargins(10, 8, 10, 8)
        controls_layout.setHorizontalSpacing(8)
        controls_layout.setVerticalSpacing(6)

        # Row 0: "Tipo:" combo, "Desde" and "Hasta" dates, then the
        # "Cliente" and "Producto" combos.
        controls_layout.addWidget(QLabel("Tipo:"), 0, 0)
        self._report_type = QComboBox()
        self._report_type.addItems(REPORT_TYPES)
        self._report_type.currentIndexChanged.connect(self._on_type_changed)
        self._report_type.setMinimumWidth(140)
        controls_layout.addWidget(self._report_type, 0, 1)

        controls_layout.addWidget(QLabel("Desde:"), 0, 2)
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate().addMonths(-1))
        self._date_from.setDisplayFormat("dd/MM/yyyy")
        controls_layout.addWidget(self._date_from, 0, 3)

        controls_layout.addWidget(QLabel("Hasta:"), 0, 4)
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setDisplayFormat("dd/MM/yyyy")
        controls_layout.addWidget(self._date_to, 0, 5)

        controls_layout.addWidget(QLabel("Cliente:"), 0, 6)
        self._filter_customer = QComboBox()
        self._filter_customer.setEditable(True)
        self._filter_customer.setMinimumWidth(140)
        self._filter_customer.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        controls_layout.addWidget(self._filter_customer, 0, 7)

        controls_layout.addWidget(QLabel("Producto:"), 0, 8)
        self._filter_product = QComboBox()
        self._filter_product.setEditable(True)
        self._filter_product.setMinimumWidth(140)
        self._filter_product.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        controls_layout.addWidget(self._filter_product, 0, 9)

        # Row 1: "Generar reporte" and "Exportar"
        btn_gen = QPushButton("Generar reporte")
        btn_gen.setProperty("success", True)
        btn_gen.clicked.connect(self._generate_report)
        controls_layout.addWidget(btn_gen, 1, 0, 1, 2)

        btn_export = QPushButton("📥 Exportar a Excel")
        btn_export.setProperty("success", True)
        btn_export.style().unpolish(btn_export)
        btn_export.style().polish(btn_export)
        btn_export.clicked.connect(self._export_to_excel)
        controls_layout.addWidget(btn_export, 1, 2, 1, 2)

        controls_layout.setColumnStretch(10, 1)
        layout.addWidget(controls)

        # ── Summary bar ──
        self._summary_label = QLabel("")
        self._summary_label.setObjectName("title-h3")
        layout.addWidget(self._summary_label)

        # ── Results table ──
        self._tabla = TablaPersonalizada()
        layout.addWidget(self._tabla, stretch=1)

        self.setLayout(layout)

    # ── Filter helpers ─────────────────────────

    def _populate_filters(self) -> None:
        """Populate customer and product filter combo boxes from DB."""
        # Customers
        self._filter_customer.clear()
        self._filter_customer.addItem("Todos", None)
        self._customer_map = {}
        customer_names: list[str] = []
        try:
            with SessionManager() as session:
                customers = session.exec(select(Customer).order_by(Customer.name)).all()
                for c in customers:
                    if c.id is not None:
                        label = f"{c.name} ({c.id_document})"
                        self._filter_customer.addItem(label, c.id)
                        self._customer_map[c.id] = label
                        customer_names.append(label)
        except Exception as e:
            log.warning("No se pudieron cargar clientes: %s", e)

        if customer_names:
            _setup_completer(self._filter_customer, customer_names)

        # Products
        self._filter_product.clear()
        self._filter_product.addItem("Todos", None)
        self._product_map = {}
        product_names: list[str] = []
        try:
            with SessionManager() as session:
                products = session.exec(select(Product).order_by(Product.name)).all()
                for p in products:
                    if p.id is not None:
                        label = p.name
                        self._filter_product.addItem(label, p.id)
                        self._product_map[p.id] = label
                        product_names.append(label)
        except Exception as e:
            log.warning("No se pudieron cargar productos: %s", e)

        if product_names:
            _setup_completer(self._filter_product, product_names)

    def _get_filter_values(self) -> tuple[int | None, int | None]:
        """Return (customer_id, product_id) from filter combos."""
        cid = self._filter_customer.currentData()
        pid = self._filter_product.currentData()
        return cid, pid

    # ── Event handlers ─────────────────────────

    def _on_type_changed(self, index: int) -> None:
        """Auto-generate when report type changes."""
        self._generate_report()

    def _generate_report(self) -> None:
        """Run the selected report query and populate the table."""
        idx = self._report_type.currentIndex()
        d_from = self._date_from.date().toPyDate()
        d_to = self._date_to.date().toPyDate()

        # Normalize to full-day range
        dt_from = datetime.combine(d_from, datetime.min.time())
        dt_to = datetime.combine(d_to, datetime.max.time())

        try:
            if idx == 0:
                data, headers, summary = self._query_ventas_por_dia(dt_from, dt_to)
            elif idx == 1:
                data, headers, summary = self._query_ventas_por_vendedor(dt_from, dt_to)
            elif idx == 2:
                data, headers, summary = self._query_productos_mas_vendidos(
                    dt_from, dt_to
                )
            elif idx == 3:
                data, headers, summary = self._query_libro_ventas(dt_from, dt_to)
            elif idx == 4:
                data, headers, summary = self._query_estado_ganancias(dt_from, dt_to)
            elif idx == 5:
                cid, pid = self._get_filter_values()
                data, headers, summary = self._query_consulta_personalizada(
                    dt_from, dt_to, customer_id=cid, product_id=pid
                )
            else:
                data, headers, summary = [], [], ""

            self._current_data = data
            self._current_headers = headers
            self._current_summary = summary

            self._tabla.clear()
            self._tabla.set_columns(headers)
            for row in data:
                self._tabla.add_row(row)
            self._summary_label.setText(summary)
            log.info(
                "reporte_generado: tipo=%s filas=%d",
                self._report_type.currentText(),
                len(data),
            )
        except Exception as e:
            log.error("Error al generar reporte: %s", e)
            self._current_data = []
            self._current_headers = []
            self._current_summary = ""
            self._tabla.clear()
            self._tabla.set_columns(["Error"])
            msg = str(e)
            if "UNIQUE constraint" in msg or "FOREIGN KEY constraint" in msg:
                friendly = "Error de integridad de datos. Verifique que los datos no estén duplicados."
            elif "no such table" in msg.lower():
                friendly = "Error de configuración de base de datos. Contacte al administrador."
            elif "database is locked" in msg.lower():
                friendly = "La base de datos está bloqueada. Intente de nuevo en unos segundos."
            else:
                friendly = f"Error al generar el reporte: {msg}"
            self._tabla.add_row([friendly])
            self._summary_label.setText("")

    # ── Export to Excel ────────────────────────

    def _export_to_excel(self) -> None:
        """Export the current report data to an Excel file."""
        if not self._current_data or not self._current_headers:
            QMessageBox.information(
                self,
                "Sin datos",
                "No hay datos para exportar. Genere un reporte primero.",
            )
            return

        suggested_name = (
            f"reporte_{self._report_type.currentText().lower().replace(' ', '_')}.xlsx"
        )
        filepath, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Guardar reporte como Excel",
            str(Path.home() / suggested_name),
            "Excel files (*.xlsx);;All files (*)",
        )
        if not filepath:
            return

        try:
            export_report_to_excel(
                filepath=filepath,
                headers=self._current_headers,
                data=self._current_data,
                title=self._report_type.currentText(),
                subtitle=self._current_summary,
            )
            QMessageBox.information(
                self,
                "Exportado",
                f"Reporte exportado exitosamente:\n{filepath}",
            )
        except Exception as e:
            log.error("Error al exportar a Excel: %s", e)
            QMessageBox.critical(
                self,
                "Error de exportación",
                f"No se pudo exportar el reporte:\n{e}",
            )

    # ── Query: sales by day ───────────────────

    @staticmethod
    def _query_ventas_por_dia(
        dt_from: datetime, dt_to: datetime
    ) -> tuple[list[list[str]], list[str], str]:
        with SessionManager() as session:
            stmt = (
                select(
                    func.date(Sale.created_at).label("day"),
                    func.count(Sale.id).label("count"),
                    func.coalesce(func.sum(Sale.total), 0).label("total"),
                    func.coalesce(func.sum(Sale.taxes), 0).label("taxes"),
                )
                .where(
                    Sale.created_at >= dt_from,  # type: ignore[reportAttributeAccessIssue]
                    Sale.created_at <= dt_to,  # type: ignore[reportAttributeAccessIssue]
                    Sale.status_id.notin_((3, 4)),  # excludes cancelled/refunded
                )
                .group_by(text("day"))
                .order_by(text("day"))
            )
            rows = session.execute(stmt).all()

        headers = ["Fecha", "Ventas", "Total Bs.", "IVA Bs."]
        data: list[list[str]] = []
        grand_total = Decimal("0")
        grand_count = 0
        for r in rows:
            day_str = (
                r.day.isoformat()
                if isinstance(r.day, (date, datetime))
                else str(r.day)
                if r.day
                else "—"
            )
            count = r.count or 0
            total = Decimal(str(r.total)) if r.total else Decimal("0")
            taxes = Decimal(str(r.taxes)) if r.taxes else Decimal("0")
            data.append([day_str, str(count), f"{total:,.2f}", f"{taxes:,.2f}"])
            grand_total += total
            grand_count += count

        summary = (
            f"Total: {grand_count} ventas  |  "
            f"Monto: Bs. {grand_total:,.2f}  |  "
            f"Período: {dt_from.strftime('%d/%m/%Y')} - {dt_to.strftime('%d/%m/%Y')}"
        )
        return data, headers, summary

    # ── Query: sales by seller ────────────────

    @staticmethod
    def _query_ventas_por_vendedor(
        dt_from: datetime, dt_to: datetime
    ) -> tuple[list[list[str]], list[str], str]:
        with SessionManager() as session:
            stmt = (
                select(
                    User.name.label("user_name"),
                    func.count(Sale.id).label("count"),
                    func.coalesce(func.sum(Sale.total), 0).label("total"),
                    func.coalesce(func.avg(Sale.total), 0).label("avg_ticket"),
                )
                .join(Sale, Sale.user_id == User.id)
                .where(
                    Sale.created_at >= dt_from,  # type: ignore[reportAttributeAccessIssue]
                    Sale.created_at <= dt_to,  # type: ignore[reportAttributeAccessIssue]
                    Sale.status_id.notin_((3, 4)),  # excludes cancelled/refunded
                )
                .group_by(User.id, User.name)
                .order_by(text("total DESC"))
            )
            rows = session.execute(stmt).all()

        headers = ["Vendedor", "Ventas", "Total Bs.", "Ticket Prom. Bs."]
        data: list[list[str]] = []
        grand_total = Decimal("0")
        grand_count = 0
        for r in rows:
            count = r.count or 0
            total = Decimal(str(r.total)) if r.total else Decimal("0")
            avg_ticket = Decimal(str(r.avg_ticket)) if r.avg_ticket else Decimal("0")
            data.append(
                [r.user_name, str(count), f"{total:,.2f}", f"{avg_ticket:,.2f}"]
            )
            grand_total += total
            grand_count += count

        summary = (
            f"Total: {grand_count} ventas  |  "
            f"Monto: Bs. {grand_total:,.2f}  |  "
            f"Período: {dt_from.strftime('%d/%m/%Y')} - {dt_to.strftime('%d/%m/%Y')}"
        )
        return data, headers, summary

    # ── Query: best selling products ──────────

    @staticmethod
    def _query_productos_mas_vendidos(
        dt_from: datetime, dt_to: datetime
    ) -> tuple[list[list[str]], list[str], str]:
        with SessionManager() as session:
            stmt = (
                select(
                    Product.name.label("product_name"),
                    func.coalesce(func.sum(SaleDetail.quantity), 0).label("qty"),
                    func.coalesce(func.sum(SaleDetail.subtotal), 0).label("total"),
                    func.count(SaleDetail.id).label("times_sold"),
                )
                .join(SaleDetail, SaleDetail.product_id == Product.id)
                .join(Sale, Sale.id == SaleDetail.sale_id)
                .where(
                    Sale.created_at >= dt_from,  # type: ignore[reportAttributeAccessIssue]
                    Sale.created_at <= dt_to,  # type: ignore[reportAttributeAccessIssue]
                    Sale.status_id.notin_((3, 4)),  # excludes cancelled/refunded
                )
                .group_by(Product.id, Product.name)
                .order_by(text("qty DESC"))
            )
            rows = session.execute(stmt).all()

        headers = ["Producto", "Cant. Vendida", "Veces Vendido", "Total Bs."]
        data: list[list[str]] = []
        grand_qty = 0
        grand_total = Decimal("0")
        for r in rows:
            qty = r.qty or 0
            total = Decimal(str(r.total)) if r.total else Decimal("0")
            times = r.times_sold or 0
            data.append([r.product_name, str(qty), str(times), f"{total:,.2f}"])
            grand_qty += qty
            grand_total += total

        summary = (
            f"Total unidades vendidas: {grand_qty}  |  "
            f"Monto: Bs. {grand_total:,.2f}  |  "
            f"Período: {dt_from.strftime('%d/%m/%Y')} - {dt_to.strftime('%d/%m/%Y')}"
        )
        return data, headers, summary

    # ── Query: sales ledger (IVA) ─────────────

    @staticmethod
    def _query_libro_ventas(
        dt_from: datetime, dt_to: datetime
    ) -> tuple[list[list[str]], list[str], str]:
        with SessionManager() as session:
            stmt = (
                select(
                    Sale.invoice_number,
                    func.date(Sale.created_at).label("day"),
                    Sale.payment_method,
                    Sale.subtotal,
                    Sale.taxes,
                    Sale.discount,
                    Sale.total,
                    Sale.user_id,
                )
                .where(
                    Sale.created_at >= dt_from,  # type: ignore[reportAttributeAccessIssue]
                    Sale.created_at <= dt_to,  # type: ignore[reportAttributeAccessIssue]
                    Sale.status_id.notin_((3, 4)),  # excludes cancelled/refunded
                )
                .order_by(Sale.created_at)
            )
            rows = session.execute(stmt).all()

            # Fetch user names for lookup
            users = session.exec(select(User)).all()
            user_map: dict[int, str] = {u.id: u.name for u in users if u.id is not None}

        headers = [
            "Factura",
            "Fecha",
            "Método Pago",
            "Subtotal Bs.",
            "IVA Bs.",
            "Dto. Bs.",
            "Total Bs.",
            "Vendedor",
        ]
        data: list[list[str]] = []
        grand_subtotal = Decimal("0")
        grand_taxes = Decimal("0")
        grand_total = Decimal("0")
        for r in rows:
            subtotal = Decimal(str(r.subtotal)) if r.subtotal else Decimal("0")
            taxes = Decimal(str(r.taxes)) if r.taxes else Decimal("0")
            discount = Decimal(str(r.discount)) if r.discount else Decimal("0")
            total = Decimal(str(r.total)) if r.total else Decimal("0")
            day_str = (
                r.day.isoformat()
                if isinstance(r.day, (date, datetime))
                else str(r.day)
                if r.day
                else "—"
            )
            seller = user_map.get(r.user_id, f"ID#{r.user_id}")

            data.append(
                [
                    r.invoice_number,
                    day_str,
                    r.payment_method,
                    f"{subtotal:,.2f}",
                    f"{taxes:,.2f}",
                    f"{discount:,.2f}",
                    f"{total:,.2f}",
                    seller,
                ]
            )
            grand_subtotal += subtotal
            grand_taxes += taxes
            grand_total += total

        summary = (
            f"Subtotal: Bs. {grand_subtotal:,.2f}  |  "
            f"IVA: Bs. {grand_taxes:,.2f}  |  "
            f"Total: Bs. {grand_total:,.2f}  |  "
            f"Período: {dt_from.strftime('%d/%m/%Y')} - {dt_to.strftime('%d/%m/%Y')}"
        )
        return data, headers, summary

    # ── Query: profit and loss ─────────────

    @staticmethod
    def _query_estado_ganancias(
        dt_from: datetime, dt_to: datetime
    ) -> tuple[list[list[str]], list[str], str]:
        with SessionManager() as session:
            # Join sale_details → sales → products to get cost + revenue per product
            stmt = (
                select(
                    Product.name.label("product_name"),
                    func.coalesce(func.sum(SaleDetail.quantity), 0).label("qty"),
                    func.coalesce(Product.cost_price_usd, 0).label("cost_price_usd"),
                    func.coalesce(
                        func.sum(SaleDetail.subtotal)
                        / func.nullif(func.sum(SaleDetail.quantity), 0),
                        0,
                    ).label("avg_sale_price"),
                    func.coalesce(
                        func.sum(SaleDetail.quantity) * Product.cost_price_usd, 0
                    ).label("total_cost"),
                    func.coalesce(func.sum(SaleDetail.subtotal), 0).label(
                        "total_revenue"
                    ),
                )
                .join(Product, Product.id == SaleDetail.product_id)
                .join(Sale, Sale.id == SaleDetail.sale_id)
                .where(
                    Sale.created_at >= dt_from,  # type: ignore[reportAttributeAccessIssue]
                    Sale.created_at <= dt_to,  # type: ignore[reportAttributeAccessIssue]
                    Sale.status_id.notin_((3, 4)),  # excludes cancelled/refunded
                )
                .group_by(Product.id, Product.name, Product.cost_price_usd)
                .order_by(text("total_revenue DESC"))
            )
            rows = session.execute(stmt).all()

        headers = [
            "Producto",
            "Cant. Vendida",
            "Costo Unit. USD",
            "Precio Prom. Bs.",
            "Costo Total USD",
            "Ingreso Total Bs.",
            "Ganancia Bs.",
            "Margen %",
        ]
        data: list[list[str]] = []
        grand_cost = Decimal("0")
        grand_revenue = Decimal("0")
        grand_profit = Decimal("0")
        rate = get_usd_rate()
        for r in rows:
            qty = r.qty or 0
            cost_price_usd = (
                Decimal(str(r.cost_price_usd)) if r.cost_price_usd else Decimal("0")
            )
            avg_price = (
                Decimal(str(r.avg_sale_price)) if r.avg_sale_price else Decimal("0")
            )
            total_cost_usd = (
                Decimal(str(r.total_cost)) if r.total_cost else Decimal("0")
            )
            total_revenue = (
                Decimal(str(r.total_revenue)) if r.total_revenue else Decimal("0")
            )

            # Convert cost to Bs for profit calculation
            cost_bs = (
                (total_cost_usd * rate).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                if rate
                else total_cost_usd
            )
            profit = (total_revenue - cost_bs).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            margin = (
                (profit / total_revenue * 100)
                if total_revenue > Decimal("0")
                else Decimal("0")
            )

            data.append(
                [
                    r.product_name,
                    str(qty),
                    f"{cost_price_usd:,.2f}",
                    f"{avg_price:,.2f}",
                    f"{total_cost_usd:,.2f}",
                    f"{total_revenue:,.2f}",
                    f"{profit:,.2f}",
                    f"{margin:.1f}%",
                ]
            )
            grand_cost += total_cost_usd
            grand_revenue += total_revenue
            grand_profit += profit

        overall_margin = (
            (grand_profit / grand_revenue * 100)
            if grand_revenue > Decimal("0")
            else Decimal("0")
        )
        # Convert cost totals to Bs for the summary line
        grand_cost_bs = (
            (grand_cost * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if rate
            else grand_cost
        )
        summary = (
            f"Ingresos: Bs. {grand_revenue:,.2f}  |  "
            f"Costo de Ventas: Bs. {grand_cost_bs:,.2f}  |  "
            f"Ganancia Neta: Bs. {grand_profit:,.2f}  |  "
            f"Margen Global: {overall_margin:.1f}%  |  "
            f"Período: {dt_from.strftime('%d/%m/%Y')} - {dt_to.strftime('%d/%m/%Y')}"
        )
        return data, headers, summary

    # ── Query: custom query ────────────────────

    @staticmethod
    def _query_consulta_personalizada(
        dt_from: datetime,
        dt_to: datetime,
        customer_id: int | None = None,
        product_id: int | None = None,
    ) -> tuple[list[list[str]], list[str], str]:
        """Sales filtered by date, customer and/or product."""
        with SessionManager() as session:
            stmt = (
                select(
                    Sale.invoice_number,
                    func.date(Sale.created_at).label("day"),
                    Customer.name.label("customer_name"),
                    Customer.id_document.label("customer_doc"),
                    Product.name.label("product_name"),
                    SaleDetail.quantity,
                    SaleDetail.unit_price,
                    SaleDetail.subtotal.label("line_subtotal"),
                    Sale.total,
                    Sale.payment_method,
                )
                .join(Customer, Customer.id == Sale.customer_id)
                .join(SaleDetail, SaleDetail.sale_id == Sale.id)
                .join(Product, Product.id == SaleDetail.product_id)
                .where(
                    Sale.created_at >= dt_from,  # type: ignore[reportAttributeAccessIssue]
                    Sale.created_at <= dt_to,  # type: ignore[reportAttributeAccessIssue]
                    Sale.status_id.notin_((3, 4)),  # excludes cancelled/refunded
                )
                .order_by(Sale.created_at, Sale.id)
            )

            if customer_id is not None:
                stmt = stmt.where(Sale.customer_id == customer_id)
            if product_id is not None:
                stmt = stmt.where(SaleDetail.product_id == product_id)

            rows = session.execute(stmt).all()

        headers = [
            "Factura",
            "Fecha",
            "Cliente",
            "Cédula",
            "Producto",
            "Cant.",
            "Precio Unit. Bs.",
            "Subtotal Bs.",
            "Total Venta Bs.",
            "Método Pago",
        ]
        data: list[list[str]] = []
        grand_qty = 0
        grand_subtotal = Decimal("0")
        for r in rows:
            qty = r.quantity or 0
            unit_price = Decimal(str(r.unit_price)) if r.unit_price else Decimal("0")
            line_subtotal = (
                Decimal(str(r.line_subtotal)) if r.line_subtotal else Decimal("0")
            )
            total = Decimal(str(r.total)) if r.total else Decimal("0")
            day_str = (
                r.day.isoformat()
                if isinstance(r.day, (date, datetime))
                else str(r.day)
                if r.day
                else "—"
            )

            data.append(
                [
                    r.invoice_number,
                    day_str,
                    r.customer_name,
                    r.customer_doc,
                    r.product_name,
                    str(qty),
                    f"{unit_price:,.2f}",
                    f"{line_subtotal:,.2f}",
                    f"{total:,.2f}",
                    r.payment_method,
                ]
            )
            grand_qty += qty
            grand_subtotal += line_subtotal

        # Build descriptor for applied filters
        filter_parts = []
        if customer_id is not None:
            filter_parts.append(f"Cliente ID {customer_id}")
        if product_id is not None:
            filter_parts.append(f"Producto ID {product_id}")
        filter_desc = f" | Filtros: {', '.join(filter_parts)}" if filter_parts else ""

        summary = (
            f"Total {len(data)} líneas  |  "
            f"Unidades: {grand_qty}  |  "
            f"Subtotal: Bs. {grand_subtotal:,.2f}  |  "
            f"Período: {dt_from.strftime('%d/%m/%Y')} - {dt_to.strftime('%d/%m/%Y')}"
            f"{filter_desc}"
        )
        return data, headers, summary
