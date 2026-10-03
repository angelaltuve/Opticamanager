"""BI dashboard with PyQtGraph: KPI cards, sales by day, by seller, top products, payment methods."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pyqtgraph as pg
from PyQt6.QtCore import QDate, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func, text
from sqlmodel import select

from opticamanager.core.logging_config import get_logger
from opticamanager.db import SessionManager
from opticamanager.models.product import Product
from opticamanager.models.sale import Sale
from opticamanager.models.sale_detail import SaleDetail
from opticamanager.models.user import User

log = get_logger(__name__)

# ── Color palette ──────────────────────────────────────────────
C_BLUE = "#3498db"
C_GREEN = "#2ecc71"
C_RED = "#e74c3c"
C_ORANGE = "#f39c12"
C_TEAL = "#1abc9c"
C_DARK = "#2c3e50"
C_GRAY = "#95a5a6"
C_WHITE = "#ffffff"

PIE_COLORS = [
    "#3498db",
    "#e74c3c",
    "#2ecc71",
    "#f39c12",
    "#9b59b6",
    "#1abc9c",
    "#e67e22",
    "#1e8449",
    "#c0392b",
    "#8e44ad",
]

# ── KPI Card ──────────────────────────────────────────────────


class _KPICard(QFrame):
    """Single KPI indicator card with title, value, and accent color."""

    _ACCENT_MAP: dict[str, str] = {
        "#3498db": "blue",
        "#2ecc71": "green",
        "#9b59b6": "purple",
        "#e74c3c": "red",
        "#f39c12": "orange",
        "#1abc9c": "teal",
    }

    def __init__(
        self, title: str, value: str, color: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("kpi-card")
        accent = self._ACCENT_MAP.get(color, "blue")
        self.setProperty("accent", accent)
        self.style().unpolish(self)
        self.style().polish(self)
        layout = QVBoxLayout()
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        lbl_title = QLabel(title)
        layout.addWidget(lbl_title)

        self._value = QLabel(value)
        self._value.setObjectName("kpi-value")
        self._value.setProperty("accent", accent)
        self._value.style().unpolish(self._value)
        self._value.style().polish(self._value)
        layout.addWidget(self._value)

        self.setLayout(layout)

    def set_value(self, value: str) -> None:
        """Update the displayed value."""
        self._value.setText(value)


# ── Pie Chart Widget ──────────────────────────────────────────


class _PieChartWidget(QWidget):
    """Custom pie chart drawn with QPainter; no external deps needed."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[tuple[str, float, str]] = []
        self._title = ""
        self.setMinimumSize(180, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, data: list[tuple[str, float, str]], title: str = "") -> None:
        """Set chart data: list of (label, value, hex_color)."""
        self._data = data
        self._title = title
        self.update()

    def paintEvent(self, a0: object) -> None:  # noqa: N802
        """Paint the pie chart with legend."""
        if not self._data:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 10
        title_h = 24 if self._title else 4

        # ── Title ──
        if self._title:
            painter.setFont(QFont("sans-serif", 11, QFont.Weight.Bold))
            painter.setPen(QColor(C_DARK))
            painter.drawText(
                0, 0, w, title_h, int(Qt.AlignmentFlag.AlignCenter), self._title
            )

        # ── Total ──
        total = sum(v for _, v, _ in self._data)
        if total <= 0:
            painter.setFont(QFont("sans-serif", 12))
            painter.setPen(QColor(C_GRAY))
            painter.drawText(
                0,
                0,
                w,
                h,
                int(Qt.AlignmentFlag.AlignCenter),
                "Sin datos",
            )
            painter.end()
            return

        # ── Pie ──
        pie_size = min(w, h - title_h - 70) - margin * 2
        pie_top = title_h + margin
        pie_left = (w - pie_size) / 2
        pie_rect = QRectF(pie_left, pie_top, pie_size, pie_size)

        start_angle = 90 * 16  # top
        for _, value, color in self._data:
            span = int(360 * (value / total) * 16)
            if span > 0:
                painter.setBrush(QColor(color))
                painter.setPen(QPen(QColor(C_WHITE), 1))
                painter.drawPie(pie_rect, start_angle, span)
            start_angle += span

        # ── Legend ──
        legend_y = pie_top + pie_size + 8
        painter.setFont(QFont("sans-serif", 9))
        x = 8
        max_w = w - 8
        for label, value, color in self._data:
            pct = (value / total) * 100
            txt = f"{label} ({pct:.1f}%)"
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(x, legend_y, 10, 10)
            painter.setPen(QColor(C_DARK))
            painter.drawText(x + 14, legend_y + 10, txt)
            x += painter.fontMetrics().horizontalAdvance(txt) + 24
            if x > max_w:
                break  # avoid overflow
        painter.end()


# ── DashboardBIView ───────────────────────────────────────────


class DashboardBIView(QWidget):
    """Business Intelligence dashboard with live PyQtGraph charts and KPI cards."""

    def __init__(self) -> None:
        super().__init__()
        self._setup_ui()
        # Defer first load so UI renders before BCV fetch (~3s HTTP call)
        QTimer.singleShot(100, self._refresh)

    # ── UI Setup ────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("bi-dashboard")
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)

        # ═══ Header ═════════════════════════════════════
        header = QHBoxLayout()
        header.setSpacing(10)

        title = QLabel("Dashboard BI")
        title.setObjectName("title-h1")
        header.addWidget(title)

        header.addStretch()

        header.addWidget(self._make_label("Desde:"))
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate().addMonths(-1))
        self._date_from.setDisplayFormat("dd/MM/yyyy")
        self._date_from.dateChanged.connect(self._refresh)
        header.addWidget(self._date_from)

        header.addWidget(self._make_label("Hasta:"))
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setDisplayFormat("dd/MM/yyyy")
        self._date_to.dateChanged.connect(self._refresh)
        header.addWidget(self._date_to)

        btn_refresh = QPushButton("🔄 Actualizar")
        btn_refresh.setProperty("success", True)
        btn_refresh.setMinimumHeight(28)
        btn_refresh.setObjectName("btn-refresh")
        btn_refresh.clicked.connect(self._refresh)
        header.addWidget(btn_refresh)

        layout.addLayout(header)

        # ═══ KPI Cards ═════════════════════════════════
        self._cards: dict[str, _KPICard] = {}
        kpi_grid = QHBoxLayout()
        kpi_grid.setSpacing(12)

        kpi_defs = [
            ("Ventas Hoy", C_GREEN, "ventas_hoy"),
            ("Ventas Mes", C_BLUE, "ventas_mes"),
            ("Productos", C_TEAL, "productos"),
            ("Stock Bajo", C_RED, "stock_bajo"),
        ]
        for label, color, key in kpi_defs:
            card = _KPICard(label, "—", color)
            self._cards[key] = card
            kpi_grid.addWidget(card, stretch=1)

        layout.addLayout(kpi_grid)

        # ═══ Charts grid (2×2) ════════════════════════
        charts_grid = QGridLayout()
        charts_grid.setSpacing(12)

        # Chart 1: sales by day (line)
        self._chart_day = pg.PlotWidget()
        self._chart_day.setBackground(C_WHITE)
        self._chart_day.setLabel("left", "Total Bs.")
        self._chart_day.setLabel("bottom", "Fecha")
        self._chart_day.showGrid(x=False, y=True, alpha=0.3)
        self._chart_day.addLegend()
        charts_grid.addWidget(self._chart_day, 0, 0)

        # Chart 2: sales by seller (bars)
        self._chart_seller = pg.PlotWidget()
        self._chart_seller.setBackground(C_WHITE)
        self._chart_seller.setLabel("left", "Total Bs.")
        self._chart_seller.setLabel("bottom", "Vendedor")
        self._chart_seller.showGrid(x=False, y=True, alpha=0.3)
        self._chart_seller.addLegend()
        charts_grid.addWidget(self._chart_seller, 0, 1)

        # Chart 3: top products (bars)
        self._chart_products = pg.PlotWidget()
        self._chart_products.setBackground(C_WHITE)
        self._chart_products.setLabel("left", "Cant. Vendida")
        self._chart_products.setLabel("bottom", "Producto")
        self._chart_products.showGrid(x=False, y=True, alpha=0.3)
        self._chart_products.addLegend()
        charts_grid.addWidget(self._chart_products, 1, 0)

        # Chart 4: payment methods (pie)
        self._chart_payment = _PieChartWidget()
        self._chart_payment.setObjectName("chart-pie")
        # background/border-radius handled by QSS #chart-pie
        charts_grid.addWidget(self._chart_payment, 1, 1)

        # Set column stretch to equal
        charts_grid.setColumnStretch(0, 1)
        charts_grid.setColumnStretch(1, 1)

        layout.addLayout(charts_grid, stretch=1)
        self.setLayout(layout)

    @staticmethod
    def _make_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("filter-label")
        return lbl

    # ── Main refresh ───────────────────────────────────

    def _refresh(self) -> None:
        """Reload all KPIs and charts."""
        d_from = self._date_from.date().toPyDate()
        d_to = self._date_to.date().toPyDate()
        dt_from = datetime.combine(d_from, datetime.min.time())
        dt_to = datetime.combine(d_to, datetime.max.time())

        log.info("Refreshing BI dashboard: %s → %s", d_from, d_to)

        try:
            self._load_kpis(dt_from, dt_to)
            self._load_sales_by_day(dt_from, dt_to)
            self._load_sales_by_seller(dt_from, dt_to)
            self._load_top_products(dt_from, dt_to)
            self._load_payment_methods(dt_from, dt_to)
        except Exception:
            log.exception("Error refreshing BI dashboard")

    # ── KPI queries ────────────────────────────────────

    def _load_kpis(self, dt_from: datetime, dt_to: datetime) -> None:
        """Query and update all KPI cards."""
        with SessionManager() as session:
            # Today's sales (using local date)
            today_start = datetime.combine(datetime.now().date(), datetime.min.time())
            today_end = datetime.combine(datetime.now().date(), datetime.max.time())

            stmt_today = select(
                func.coalesce(func.count(Sale.id), 0).label("count"),
                func.coalesce(func.sum(Sale.total), 0).label("total"),
            ).where(
                Sale.created_at >= today_start,  # type: ignore[reportAttributeAccessIssue]
                Sale.created_at <= today_end,  # type: ignore[reportAttributeAccessIssue]
                Sale.status_id.notin_((3, 4)),  # excludes cancelled/refunded
            )
            today_result = session.execute(stmt_today).one()
            ventas_hoy_ct = today_result.count
            ventas_hoy_total = Decimal(str(today_result.total))

            # This month sales
            month_start = dt_from.replace(day=1, hour=0, minute=0, second=0)
            if month_start < dt_from:
                month_start = dt_from
            stmt_month = select(
                func.coalesce(func.sum(Sale.total), 0),
            ).where(
                Sale.created_at >= month_start,  # type: ignore[reportAttributeAccessIssue]
                Sale.created_at <= dt_to,  # type: ignore[reportAttributeAccessIssue]
                Sale.status_id.notin_((3, 4)),  # excludes cancelled/refunded
            )
            ventas_mes_total = Decimal(
                str(session.execute(stmt_month).scalar_one() or 0)
            )

            # Active products
            total_products = session.exec(
                select(func.count(Product.id)).where(Product.active == True)  # noqa: E712
            ).one()

            # Low stock
            low_stock = session.exec(
                select(func.count(Product.id)).where(
                    Product.stock_quantity < Product.min_stock,
                    Product.active == True,  # noqa: E712
                )
            ).one()

        self._cards["ventas_hoy"].set_value(
            f"{ventas_hoy_ct}  ·  Bs. {ventas_hoy_total:,.2f}"
        )
        self._cards["ventas_mes"].set_value(f"Bs. {ventas_mes_total:,.2f}")
        self._cards["productos"].set_value(str(total_products))
        self._cards["stock_bajo"].set_value(str(low_stock))

        # ── Chart: sales by day ───────────────────────────

    def _load_sales_by_day(self, dt_from: datetime, dt_to: datetime) -> None:
        """Line chart of daily sales over the selected period."""
        with SessionManager() as session:
            stmt = (
                select(
                    func.date(Sale.created_at).label("day"),
                    func.coalesce(func.sum(Sale.total), 0).label("total"),
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

        if not rows:
            self._chart_day.clear()
            self._chart_day.addItem(
                pg.TextItem("Sin datos en el período", color=C_GRAY)
            )
            return

        # Convert dates to POSIX timestamps for DateAxisItem
        import time as _time

        dates = []
        values = []
        for r in rows:
            if r.day is None:
                continue
            # Parse ISO date string to datetime -> timestamp
            dt = datetime.strptime(r.day, "%Y-%m-%d")
            ts = _time.mktime(dt.timetuple())
            dates.append(ts)
            values.append(float(r.total))

        self._chart_day.clear()
        self._chart_day.plot(
            dates,
            values,
            pen=pg.mkPen(C_BLUE, width=2),
            symbol="o",
            symbolSize=6,
            symbolBrush=C_BLUE,
            name="Total Bs.",
        )

        # Use DateAxisItem for the bottom axis
        axis = pg.DateAxisItem(orientation="bottom")
        self._chart_day.setAxisItems({"bottom": axis})

        # ── Chart: sales by seller ────────────────────────

    def _load_sales_by_seller(self, dt_from: datetime, dt_to: datetime) -> None:
        """Horizontal bar chart of sales by seller."""
        with SessionManager() as session:
            stmt = (
                select(
                    User.name.label("user_name"),  # type: ignore[attr-defined]
                    func.coalesce(func.sum(Sale.total), 0).label("total"),
                )
                .join(Sale, Sale.user_id == User.id)
                .where(
                    Sale.created_at >= dt_from,  # type: ignore[reportAttributeAccessIssue]
                    Sale.created_at <= dt_to,  # type: ignore[reportAttributeAccessIssue],
                    Sale.status_id.notin_((3, 4)),  # excludes cancelled/refunded
                )
                .group_by(User.id, User.name)
                .order_by(text("total DESC"))
            )
            rows = session.execute(stmt).all()

        self._chart_seller.clear()
        if not rows:
            self._chart_seller.addItem(pg.TextItem("Sin datos", color=C_GRAY))
            return

        names = [r.user_name for r in rows]
        totals = [float(r.total) for r in rows]
        y_pos = list(range(len(names)))

        bars = pg.BarGraphItem(
            x0=0,
            x1=totals,
            y=y_pos,
            height=0.6,
            brush=pg.mkBrush(C_GREEN),
            pen=pg.mkPen(C_WHITE, width=1),
        )
        self._chart_seller.addItem(bars)

        # Names on Y-axis (left), values on X-axis (bottom)
        ay = self._chart_seller.getAxis("left")
        ay.setTicks([[(i, n) for i, n in enumerate(names)]])
        self._chart_seller.setLabel("bottom", "Total Bs.")
        self._chart_seller.setLabel("left", "Vendedor")

        # Highest seller at top
        self._chart_seller.invertY(True)
        self._chart_seller.autoRange()

        # ── Chart: top products ───────────────────────────

    def _load_top_products(self, dt_from: datetime, dt_to: datetime) -> None:
        """Horizontal bar chart of top 10 products by quantity sold."""
        with SessionManager() as session:
            stmt = (
                select(
                    Product.name.label("product_name"),  # type: ignore[attr-defined]
                    func.coalesce(func.sum(SaleDetail.quantity), 0).label("qty"),
                )
                .join(SaleDetail, SaleDetail.product_id == Product.id)
                .join(Sale, Sale.id == SaleDetail.sale_id)
                .where(
                    Sale.created_at >= dt_from,  # type: ignore[reportAttributeAccessIssue]
                    Sale.created_at <= dt_to,  # type: ignore[reportAttributeAccessIssue],
                    Sale.status_id.notin_((3, 4)),  # excludes cancelled/refunded
                )
                .group_by(Product.id, Product.name)
                .order_by(text("qty DESC"))
                .limit(10)
            )
            rows = session.execute(stmt).all()

        self._chart_products.clear()
        if not rows:
            self._chart_products.addItem(pg.TextItem("Sin datos", color=C_GRAY))
            return

        names = []
        qtys = []
        for r in rows:
            n = r.product_name
            # Let names be full width; pyqtgraph will truncate display if needed
            names.append(n)
            qtys.append(float(r.qty))

        y_pos = list(range(len(names)))
        bars = pg.BarGraphItem(
            x0=0,
            x1=qtys,
            y=y_pos,
            height=0.6,
            brush=pg.mkBrush(C_ORANGE),
            pen=pg.mkPen(C_WHITE, width=1),
        )
        self._chart_products.addItem(bars)

        # Names on Y-axis (left), values on X-axis (bottom)
        ay = self._chart_products.getAxis("left")
        ay.setTicks([[(i, n) for i, n in enumerate(names)]])
        self._chart_products.setLabel("bottom", "Cant. Vendida")
        self._chart_products.setLabel("left", "Producto")

        # Most sold at top
        self._chart_products.invertY(True)
        self._chart_products.autoRange()

        # ── Chart: payment methods ─────────────────────────

    def _load_payment_methods(self, dt_from: datetime, dt_to: datetime) -> None:
        """Pie chart of payment method distribution by total amount."""
        with SessionManager() as session:
            stmt = (
                select(
                    Sale.payment_method,
                    func.coalesce(func.sum(Sale.total), 0).label("total"),
                )
                .where(
                    Sale.created_at >= dt_from,  # type: ignore[reportAttributeAccessIssue]
                    Sale.created_at <= dt_to,  # type: ignore[reportAttributeAccessIssue],
                    Sale.status_id.notin_((3, 4)),  # excludes cancelled/refunded
                )
                .group_by(Sale.payment_method)
                .order_by(text("total DESC"))
            )
            rows = session.execute(stmt).all()

        if not rows:
            self._chart_payment.set_data([], "Métodos de Pago")
            return

        data: list[tuple[str, float, str]] = []
        for i, r in enumerate(rows):
            color = PIE_COLORS[i % len(PIE_COLORS)]
            data.append((r.payment_method, float(r.total), color))

        self._chart_payment.set_data(data, "Métodos de Pago")
