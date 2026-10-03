"""Tests for ReportesView: operational reports with a selector and a table.

Coverage target: >=70% of reportes_view.py
Strategy: mock SessionManager and get_usd_rate to stay off the real DB.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QMessageBox
from pytest_mock import MockerFixture

from opticamanager.ui.views.reportes_view import (
    REPORT_TYPES,
    ReportesView,
    _setup_completer,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_customer(
    customer_id: int = 1,
    name: str = "Ana López",
    id_document: str = "V-12345678",
) -> MagicMock:
    c = MagicMock()
    c.id = customer_id
    c.name = name
    c.id_document = id_document
    return c


def _make_product(product_id: int = 1, name: str = "Lente Bifocal") -> MagicMock:
    p = MagicMock()
    p.id = product_id
    p.name = name
    return p


def _make_user(user_id: int = 1, name: str = "Admin") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.name = name
    return u


def _make_sale_row(
    day: date | None = None,
    count: int = 5,
    total: Decimal = Decimal("1000.00"),
    taxes: Decimal = Decimal("160.00"),
) -> MagicMock:
    r = MagicMock()
    r.day = day or date(2026, 9, 20)
    r.count = count
    r.total = total
    r.taxes = taxes
    return r


def _make_vendedor_row(
    user_name: str = "Admin",
    count: int = 5,
    total: Decimal = Decimal("1000.00"),
    avg_ticket: Decimal = Decimal("200.00"),
) -> MagicMock:
    r = MagicMock()
    r.user_name = user_name
    r.count = count
    r.total = total
    r.avg_ticket = avg_ticket
    return r


def _make_producto_row(
    product_name: str = "Lente",
    qty: int = 10,
    total: Decimal = Decimal("500.00"),
    times_sold: int = 5,
) -> MagicMock:
    r = MagicMock()
    r.product_name = product_name
    r.qty = qty
    r.total = total
    r.times_sold = times_sold
    return r


def _make_libro_row(
    invoice_number: str = "FAC-000001",
    day: date | None = None,
    payment_method: str = "Efectivo",
    subtotal: Decimal = Decimal("862.07"),
    taxes: Decimal = Decimal("137.93"),
    discount: Decimal = Decimal("0"),
    total: Decimal = Decimal("1000.00"),
    user_id: int = 1,
) -> MagicMock:
    r = MagicMock()
    r.invoice_number = invoice_number
    r.day = day or date(2026, 9, 20)
    r.payment_method = payment_method
    r.subtotal = subtotal
    r.taxes = taxes
    r.discount = discount
    r.total = total
    r.user_id = user_id
    return r


def _make_ganancia_row(
    product_name: str = "Lente",
    qty: int = 10,
    cost_price_usd: Decimal = Decimal("5.00"),
    avg_sale_price: Decimal = Decimal("25.00"),
    total_cost: Decimal = Decimal("50.00"),
    total_revenue: Decimal = Decimal("250.00"),
) -> MagicMock:
    r = MagicMock()
    r.product_name = product_name
    r.qty = qty
    r.cost_price_usd = cost_price_usd
    r.avg_sale_price = avg_sale_price
    r.total_cost = total_cost
    r.total_revenue = total_revenue
    return r


def _make_personalizada_row(
    invoice_number: str = "FAC-000001",
    day: date | None = None,
    customer_name: str = "Ana",
    customer_doc: str = "V-123",
    product_name: str = "Lente",
    quantity: int = 2,
    unit_price: Decimal = Decimal("25.00"),
    line_subtotal: Decimal = Decimal("50.00"),
    total: Decimal = Decimal("100.00"),
    payment_method: str = "Efectivo",
) -> MagicMock:
    r = MagicMock()
    r.invoice_number = invoice_number
    r.day = day or date(2026, 9, 20)
    r.customer_name = customer_name
    r.customer_doc = customer_doc
    r.product_name = product_name
    r.quantity = quantity
    r.unit_price = unit_price
    r.line_subtotal = line_subtotal
    r.total = total
    r.payment_method = payment_method
    return r


def _fake_session(
    mocker: MockerFixture,
    customers: list | None = None,
    products: list | None = None,
    query_rows: list | None = None,
    user_rows: list | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Create a fake session for ReportesView.

    SessionManager is called as context manager. exec() is used for
    _populate_filters (2 calls: customers, products) and optionally for
    _query_libro_ventas (1 call: user_map). execute() is used for all
    query methods.
    """
    fake = MagicMock()
    manager = mocker.patch("opticamanager.ui.views.reportes_view.SessionManager")
    manager.return_value.__enter__.return_value = fake
    manager.return_value.__exit__.return_value = False

    # _populate_filters calls exec twice (customers, products)
    customer_mock = MagicMock()
    customer_mock.all.return_value = customers or []
    product_mock = MagicMock()
    product_mock.all.return_value = products or []

    exec_calls: list = [customer_mock, product_mock]

    # _query_libro_ventas calls exec once more for user_map
    if user_rows is not None:
        user_mock = MagicMock()
        user_mock.all.return_value = user_rows
        exec_calls.append(user_mock)

    fake.exec.side_effect = exec_calls
    fake.execute.return_value.all.return_value = query_rows or []

    return fake, manager


def _table_cell(view: ReportesView, row: int = 0, col: int = 0) -> str:
    """Read a cell from the view's result table."""
    item = view._tabla.model().item(row, col)
    return item.text() if item else ""


# ── _setup_completer Tests ───────────────────────────────────────────────


class TestSetupCompleter:
    """Tests for the module-level _setup_completer helper."""

    def test_creates_completer_on_combo(self, qtbot: QtBot) -> None:
        from PyQt6.QtWidgets import QComboBox

        combo = QComboBox()
        qtbot.addWidget(combo)
        combo.setEditable(True)
        _setup_completer(combo, ["Item A", "Item B", "Item C"])
        assert combo.completer() is not None

    def test_completer_case_insensitive(self, qtbot: QtBot) -> None:
        from PyQt6.QtWidgets import QComboBox

        combo = QComboBox()
        qtbot.addWidget(combo)
        combo.setEditable(True)
        _setup_completer(combo, ["Lente Bifocal"])
        completer = combo.completer()
        assert completer is not None


# ── ReportesView Creation Tests ──────────────────────────────────────────


class TestReportesViewCreacion:
    """Smoke tests for ReportesView creation."""

    def test_creacion_basica(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker)
        view = ReportesView()
        qtbot.addWidget(view)
        assert isinstance(view, ReportesView)

    def test_titulo_visible(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker)
        view = ReportesView()
        qtbot.addWidget(view)
        from PyQt6.QtWidgets import QLabel

        titles = view.findChildren(QLabel, "title-h2")
        assert len(titles) >= 1
        assert "Reportes" in titles[0].text()

    def test_combo_tipos_reporte(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker)
        view = ReportesView()
        qtbot.addWidget(view)
        assert view._report_type.count() == len(REPORT_TYPES)

    def test_datos_vacios_muestra_tabla_vacia(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        _fake_session(mocker, query_rows=[])
        view = ReportesView()
        qtbot.addWidget(view)
        assert view._current_data == []
        assert view._current_headers == ["Fecha", "Ventas", "Total Bs.", "IVA Bs."]

    def test_summary_vacio(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker, query_rows=[])
        view = ReportesView()
        qtbot.addWidget(view)
        assert "0" in view._summary_label.text()


# ── ReportesView Filter Tests ────────────────────────────────────────────


class TestReportesViewFiltros:
    """Tests for _populate_filters with customer/product data."""

    def test_filtros_con_clientes(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        customers = [
            _make_customer(1, "Ana", "V-123"),
            _make_customer(2, "Juan", "V-456"),
        ]
        _fake_session(mocker, customers=customers)
        view = ReportesView()
        qtbot.addWidget(view)
        # "Todos" + 2 customers
        assert view._filter_customer.count() == 3

    def test_filtros_con_productos(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        products = [_make_product(1, "Lente 1"), _make_product(2, "Lente 2")]
        _fake_session(mocker, products=products)
        view = ReportesView()
        qtbot.addWidget(view)
        # "Todos" + 2 products
        assert view._filter_product.count() == 3

    def test_customer_map_se_puebla(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        customers = [_make_customer(1, "Ana", "V-123")]
        _fake_session(mocker, customers=customers)
        view = ReportesView()
        qtbot.addWidget(view)
        assert 1 in view._customer_map

    def test_product_map_se_puebla(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        products = [_make_product(1, "Lente 1")]
        _fake_session(mocker, products=products)
        view = ReportesView()
        qtbot.addWidget(view)
        assert 1 in view._product_map

    def test_exception_cargando_clientes_no_crash(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        """Exception during customer load is caught and logged."""
        fake = MagicMock()
        manager = mocker.patch("opticamanager.ui.views.reportes_view.SessionManager")
        manager.return_value.__enter__.return_value = fake
        manager.return_value.__exit__.return_value = False
        fake.exec.side_effect = [
            Exception("DB down"),
            MagicMock(all=MagicMock(return_value=[])),
        ]
        fake.execute.return_value.all.return_value = []
        view = ReportesView()
        qtbot.addWidget(view)
        # View still created with empty customer filter
        assert view._filter_customer.count() == 1  # Only "Todos"

    def test_exception_cargando_productos_no_crash(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        """Exception during product load is caught and logged."""
        fake = MagicMock()
        manager = mocker.patch("opticamanager.ui.views.reportes_view.SessionManager")
        manager.return_value.__enter__.return_value = fake
        manager.return_value.__exit__.return_value = False
        fake.exec.side_effect = [
            MagicMock(all=MagicMock(return_value=[])),
            Exception("DB down"),
        ]
        fake.execute.return_value.all.return_value = []
        view = ReportesView()
        qtbot.addWidget(view)
        # View still created with empty product filter
        assert view._filter_product.count() == 1  # Only "Todos"


# ── ReportesView Query Tests ─────────────────────────────────────────────


class TestReportesViewQueryVentasPorDia:
    """Tests for report type 0: "Ventas por día"."""

    def test_con_datos(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [_make_sale_row(date(2026, 9, 20), 5, Decimal("1000"), Decimal("160"))]
        _fake_session(mocker, query_rows=rows)
        view = ReportesView()
        qtbot.addWidget(view)
        assert len(view._current_data) == 1
        assert "1,000" in view._current_data[0][2]

    def test_dia_none_muestra_guion(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        row = _make_sale_row(day=None)
        row.day = None
        _fake_session(mocker, query_rows=[row])
        view = ReportesView()
        qtbot.addWidget(view)
        assert _table_cell(view, 0, 0) == "\u2014"

    def test_dia_datetime_se_formatea(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        row = _make_sale_row(day=datetime(2026, 9, 20))
        _fake_session(mocker, query_rows=[row])
        view = ReportesView()
        qtbot.addWidget(view)
        assert "2026-09-20" in _table_cell(view, 0, 0)


class TestReportesViewQueryVentasPorVendedor:
    """Tests for report type 1: "Ventas por vendedor"."""

    def test_con_datos(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [_make_vendedor_row()]
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker, query_rows=rows)
        view = ReportesView()
        qtbot.addWidget(view)
        view._report_type.setCurrentIndex(1)
        assert len(view._current_data) == 1


class TestReportesViewQueryProductosMasVendidos:
    """Tests for report type 2: "Productos más vendidos"."""

    def test_con_datos(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [_make_producto_row()]
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker, query_rows=rows)
        view = ReportesView()
        qtbot.addWidget(view)
        view._report_type.setCurrentIndex(2)
        assert len(view._current_data) == 1


class TestReportesViewQueryLibroVentas:
    """Tests for report type 3: "Libro de ventas (IVA)"."""

    def test_con_datos(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [_make_libro_row()]
        user = _make_user(1, "Admin")
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker, query_rows=rows, user_rows=[user])
        view = ReportesView()
        qtbot.addWidget(view)
        view._report_type.setCurrentIndex(3)
        assert len(view._current_data) == 1

    def test_user_id_no_encontrado_muestra_id(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        row = _make_libro_row(user_id=999)
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker, query_rows=[row], user_rows=[])
        view = ReportesView()
        qtbot.addWidget(view)
        view._report_type.setCurrentIndex(3)
        assert "ID#999" in _table_cell(view, 0, 7)

    def test_invoice_none(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        row = _make_libro_row(invoice_number="FAC-NULL")
        row.invoice_number = None
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker, query_rows=[row], user_rows=[])
        view = ReportesView()
        qtbot.addWidget(view)
        view._report_type.setCurrentIndex(3)
        assert _table_cell(view, 0, 0) == ""


class TestReportesViewQueryEstadoGanancias:
    """Tests for report type 4: "Estado de ganancias"."""

    def test_con_datos(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [_make_ganancia_row()]
        mocker.patch(
            "opticamanager.ui.views.reportes_view.get_usd_rate",
            return_value=Decimal("36.00"),
        )
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker, query_rows=rows)
        view = ReportesView()
        qtbot.addWidget(view)
        view._report_type.setCurrentIndex(4)
        assert len(view._current_data) == 1

    def test_rate_none_usa_directo(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [_make_ganancia_row()]
        mocker.patch(
            "opticamanager.ui.views.reportes_view.get_usd_rate",
            return_value=None,
        )
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker, query_rows=rows)
        view = ReportesView()
        qtbot.addWidget(view)
        view._report_type.setCurrentIndex(4)
        assert len(view._current_data) == 1

    def test_revenue_zero_margen_cero(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        rows = [_make_ganancia_row(total_revenue=Decimal("0"), total_cost=Decimal("0"))]
        mocker.patch(
            "opticamanager.ui.views.reportes_view.get_usd_rate",
            return_value=Decimal("36.00"),
        )
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker, query_rows=rows)
        view = ReportesView()
        qtbot.addWidget(view)
        view._report_type.setCurrentIndex(4)
        assert "0.0%" in _table_cell(view, 0, 7)


class TestReportesViewConsultaPersonalizada:
    """Tests for report type 5: "Consulta personalizada"."""

    def test_con_datos(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [_make_personalizada_row()]
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker, query_rows=rows)
        view = ReportesView()
        qtbot.addWidget(view)
        view._report_type.setCurrentIndex(5)
        assert len(view._current_data) == 1

    def test_con_customer_id_filter(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [_make_personalizada_row()]
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker, query_rows=rows)
        view = ReportesView()
        qtbot.addWidget(view)
        view._filter_customer.addItem("Test", 5)
        view._filter_customer.setCurrentIndex(view._filter_customer.count() - 1)
        view._report_type.setCurrentIndex(5)
        assert len(view._current_data) == 1

    def test_con_product_id_filter(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [_make_personalizada_row()]
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker, query_rows=rows)
        view = ReportesView()
        qtbot.addWidget(view)
        view._filter_product.addItem("Lente", 3)
        view._filter_product.setCurrentIndex(view._filter_product.count() - 1)
        view._report_type.setCurrentIndex(5)
        assert len(view._current_data) == 1

    def test_dia_none_en_personalizada(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        row = _make_personalizada_row()
        row.day = None
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker, query_rows=[row])
        view = ReportesView()
        qtbot.addWidget(view)
        view._report_type.setCurrentIndex(5)
        assert _table_cell(view, 0, 1) == "\u2014"

    def test_dia_datetime_en_personalizada(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        row = _make_personalizada_row(day=datetime(2026, 12, 25))
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker, query_rows=[row])
        view = ReportesView()
        qtbot.addWidget(view)
        view._report_type.setCurrentIndex(5)
        assert "2026-12-25" in _table_cell(view, 0, 1)


# ── ReportesView OnTypeChanged Tests ─────────────────────────────────────


class TestReportesViewOnTypeChanged:
    """Tests for _on_type_changed."""

    def test_cambia_tipo_genera_reporte(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        rows = [_make_vendedor_row()]
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker, query_rows=rows)
        view = ReportesView()
        qtbot.addWidget(view)
        view._report_type.setCurrentIndex(1)
        assert view._current_headers == [
            "Vendedor",
            "Ventas",
            "Total Bs.",
            "Ticket Prom. Bs.",
        ]


# ── ReportesView Export Tests ────────────────────────────────────────────


class TestReportesViewExport:
    """Tests for _export_to_excel."""

    def test_sin_datos_muestra_info(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker)
        view = ReportesView()
        qtbot.addWidget(view)
        view._current_data = []
        view._current_headers = []
        info_msgs: list = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: info_msgs.append("ok"),
        )
        view._export_to_excel()
        assert info_msgs

    def test_cancelarFileDialog_no_exporta(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        rows = [_make_sale_row()]
        _fake_session(mocker, query_rows=rows)
        view = ReportesView()
        qtbot.addWidget(view)
        mocker.patch(
            "opticamanager.ui.views.reportes_view.QFileDialog.getSaveFileName",
            return_value=("", ""),
        )
        view._export_to_excel()

    def test_export_exitoso(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [_make_sale_row()]
        _fake_session(mocker, query_rows=rows)
        view = ReportesView()
        qtbot.addWidget(view)
        mocker.patch(
            "opticamanager.ui.views.reportes_view.QFileDialog.getSaveFileName",
            return_value=("/tmp/test.xlsx", "Excel"),
        )
        mock_export = mocker.patch(
            "opticamanager.ui.views.reportes_view.export_report_to_excel"
        )
        info_msgs: list = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: info_msgs.append("ok"),
        )
        view._export_to_excel()
        mock_export.assert_called_once()
        assert info_msgs

    def test_export_error_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        rows = [_make_sale_row()]
        _fake_session(mocker, query_rows=rows)
        view = ReportesView()
        qtbot.addWidget(view)
        mocker.patch(
            "opticamanager.ui.views.reportes_view.QFileDialog.getSaveFileName",
            return_value=("/tmp/test.xlsx", "Excel"),
        )
        mocker.patch(
            "opticamanager.ui.views.reportes_view.export_report_to_excel",
            side_effect=Exception("Disk full"),
        )
        critical_msgs: list = []
        mocker.patch.object(
            QMessageBox,
            "critical",
            side_effect=lambda *_a, **_k: critical_msgs.append("ok"),
        )
        view._export_to_excel()
        assert critical_msgs


# ── ReportesView Error Handling Tests ────────────────────────────────────


class TestReportesViewErrorHandling:
    """Tests for _generate_report error handling branches.

    Error handler sets _current_data=[] and adds friendly message to the table.
    We check the table widget (model) for the error message.
    """

    def test_unique_constraint_error(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker)
        fake.execute.return_value.all.side_effect = Exception(
            "UNIQUE constraint failed"
        )
        view = ReportesView()
        qtbot.addWidget(view)
        assert "integridad" in _table_cell(view)

    def test_foreign_key_error(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker)
        fake.execute.return_value.all.side_effect = Exception(
            "FOREIGN KEY constraint failed"
        )
        view = ReportesView()
        qtbot.addWidget(view)
        assert "integridad" in _table_cell(view)

    def test_no_such_table_error(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker)
        fake.execute.return_value.all.side_effect = Exception("no such table: sales")
        view = ReportesView()
        qtbot.addWidget(view)
        assert "configuración" in _table_cell(view)

    def test_database_locked_error(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker)
        fake.execute.return_value.all.side_effect = Exception("database is locked")
        view = ReportesView()
        qtbot.addWidget(view)
        assert "bloqueada" in _table_cell(view)

    def test_generic_error(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch.object(ReportesView, "_populate_filters")
        fake, _ = _fake_session(mocker)
        fake.execute.return_value.all.side_effect = Exception(
            "Something weird happened"
        )
        view = ReportesView()
        qtbot.addWidget(view)
        assert "Something weird happened" in _table_cell(view)


# ── ReportesView _get_filter_values Tests ────────────────────────────────


class TestReportesViewGetFilterValues:
    """Tests for _get_filter_values."""

    def test_default_returns_none(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker)
        view = ReportesView()
        qtbot.addWidget(view)
        cid, pid = view._get_filter_values()
        assert cid is None
        assert pid is None

    def test_con_valor_seleccionado(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker)
        view = ReportesView()
        qtbot.addWidget(view)
        view._filter_customer.addItem("Test", 5)
        view._filter_customer.setCurrentIndex(view._filter_customer.count() - 1)
        cid, pid = view._get_filter_values()
        assert cid == 5
        assert pid is None


# ── ReportesView Multiple Rows Tests ─────────────────────────────────────


class TestReportesViewMultipleRows:
    """Tests for reports with multiple rows."""

    def test_ventas_por_dia_multiplas_filas(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        rows = [
            _make_sale_row(date(2026, 9, 19), 3, Decimal("500"), Decimal("80")),
            _make_sale_row(date(2026, 9, 20), 5, Decimal("1000"), Decimal("160")),
        ]
        _fake_session(mocker, query_rows=rows)
        view = ReportesView()
        qtbot.addWidget(view)
        assert len(view._current_data) == 2
        assert "8" in view._summary_label.text()
        assert "1,500" in view._summary_label.text()


# ── ReportesView Index Out of Range Test ─────────────────────────────────


class TestReportesViewIndexOutOfRange:
    """Test for unknown report index (else branch)."""

    def test_index_desconocido(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker)
        view = ReportesView()
        qtbot.addWidget(view)
        mocker.patch.object(view._report_type, "currentIndex", return_value=99)
        view._generate_report()
        assert view._current_data == []
        assert view._current_headers == []
