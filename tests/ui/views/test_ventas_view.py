"""Tests for VentasView: sales history and refunds."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QPushButton
from pytest_mock import MockerFixture

from opticamanager.models.sale import Sale
from opticamanager.ui.views.ventas_view import VentasView

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_sale(
    sale_id: int = 1,
    invoice: str = "FAC-000001",
    total: Decimal = Decimal("100.00"),
    status_id: int = 1,
) -> MagicMock:
    sale = MagicMock(spec=Sale)
    sale.id = sale_id
    sale.invoice_number = invoice
    sale.total = total
    sale.status_id = status_id
    sale.created_at = datetime(2026, 9, 20)
    return sale


def _make_row(
    sale: MagicMock,
    customer: str = "Ana López",
    user: str = "Admin User",
    status: str = "Completada",
) -> tuple:
    return (sale, customer, user, status)


def _fake_session(mocker: MockerFixture, rows: list | None = None):
    """Create a fake session returning controlled rows (4-tuples)."""
    fake = MagicMock()
    manager = mocker.patch("opticamanager.ui.views.ventas_view.SessionManager")
    manager.return_value.__enter__.return_value = fake
    manager.return_value.__exit__.return_value = False

    if rows is None:
        rows = []
    fake.exec.return_value.all.return_value = rows
    return fake, manager


# ── Creation ─────────────────────────────────────────────────────────


class TestVentasViewCreacion:
    """Smoke tests for VentasView creation and UI setup."""

    def test_creacion_basica(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker, rows=[])
        view = VentasView()
        qtbot.addWidget(view)
        assert isinstance(view, VentasView)

    def test_tabla_columnas(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker, rows=[])
        view = VentasView()
        qtbot.addWidget(view)
        assert view._table.columnCount() == 7
        headers = [view._table.horizontalHeaderItem(i).text() for i in range(7)]
        assert headers == [
            "Fecha",
            "Factura",
            "Cliente",
            "Vendedor",
            "Total Bs",
            "Estado",
            "",
        ]

    def test_search_placeholder(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker, rows=[])
        view = VentasView()
        qtbot.addWidget(view)
        assert "factura" in view._search_input.placeholderText().lower()
        assert "cliente" in view._search_input.placeholderText().lower()

    def test_summary_vacio(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker, rows=[])
        view = VentasView()
        qtbot.addWidget(view)
        assert "0" in view._summary_label.text()


# ── Data loading ───────────────────────────────────────────────────────


class TestVentasViewCargaDatos:
    """Tests for _load_ventas populating the table."""

    def test_carga_una_venta(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        sale = _make_sale(total=Decimal("200.00"))
        _fake_session(mocker, rows=[_make_row(sale)])
        view = VentasView()
        qtbot.addWidget(view)
        assert view._table.rowCount() == 1
        assert view._table.item(0, 0).text() == "20/09/2026"
        assert view._table.item(0, 1).text() == "FAC-000001"
        assert view._table.item(0, 2).text() == "Ana López"
        assert view._table.item(0, 3).text() == "Admin User"
        assert "200" in view._table.item(0, 4).text()
        assert view._table.item(0, 5).text() == "Completada"
        assert "200" in view._summary_label.text()

    def test_carga_varias_ventas(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [
            _make_row(_make_sale(1, "FAC-000001", Decimal("100.00"))),
            _make_row(_make_sale(2, "FAC-000002", Decimal("250.00"))),
            _make_row(_make_sale(3, "FAC-000003", Decimal("50.00"))),
        ]
        _fake_session(mocker, rows=rows)
        view = VentasView()
        qtbot.addWidget(view)
        assert view._table.rowCount() == 3
        assert "400" in view._summary_label.text()

    def test_fecha_none_muestra_guion(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        sale = _make_sale()
        sale.created_at = None
        _fake_session(mocker, rows=[_make_row(sale)])
        view = VentasView()
        qtbot.addWidget(view)
        assert view._table.item(0, 0).text() == "—"

    def test_celdas_no_editables(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker, rows=[_make_row(_make_sale())])
        view = VentasView()
        qtbot.addWidget(view)
        for col in range(6):
            item = view._table.item(0, col)
            if item is not None:
                assert not (item.flags() & Qt.ItemFlag.ItemIsEditable)


# ── Search ────────────────────────────────────────────────────────────


class TestVentasViewBusqueda:
    """Tests for search filtering."""

    def test_filtro_por_factura(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [
            _make_row(_make_sale(1, "FAC-000001"), customer="Ana López"),
            _make_row(_make_sale(2, "FAC-000002"), customer="Carlos Ruiz"),
        ]
        _fake_session(mocker, rows=rows)
        view = VentasView()
        qtbot.addWidget(view)
        assert view._table.rowCount() == 2
        view._search_input.setText("FAC-000002")
        assert view._table.rowCount() == 1
        assert view._table.item(0, 1).text() == "FAC-000002"

    def test_filtro_por_cliente(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [
            _make_row(_make_sale(1, "FAC-000001"), customer="Ana López"),
            _make_row(_make_sale(2, "FAC-000002"), customer="Ana García"),
            _make_row(_make_sale(3, "FAC-000003"), customer="Carlos Ruiz"),
        ]
        _fake_session(mocker, rows=rows)
        view = VentasView()
        qtbot.addWidget(view)
        view._search_input.setText("ana")
        assert view._table.rowCount() == 2

    def test_filtro_sin_resultados(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker, rows=[_make_row(_make_sale())])
        view = VentasView()
        qtbot.addWidget(view)
        view._search_input.setText("ZZZZ")
        assert view._table.rowCount() == 0


# ── Refund button ─────────────────────────────────────────────────────


class TestVentasViewBotonRembolsar:
    """Tests for the refund button visibility."""

    def test_boton_visible_para_venta_completada(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        _fake_session(mocker, rows=[_make_row(_make_sale(status_id=1))])
        view = VentasView()
        qtbot.addWidget(view)
        btn_widget = view._table.cellWidget(0, 6)
        assert btn_widget is not None
        btns = btn_widget.findChildren(QPushButton)
        assert len(btns) == 1
        assert "Rembolsar" in btns[0].text()

    def test_boton_oculto_para_venta_rembolsada(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        _fake_session(
            mocker,
            rows=[_make_row(_make_sale(status_id=4), status="Rembolsada")],
        )
        view = VentasView()
        qtbot.addWidget(view)
        assert view._table.cellWidget(0, 6) is None

    def test_boton_oculto_para_venta_cancelada(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        _fake_session(
            mocker,
            rows=[_make_row(_make_sale(status_id=3), status="Cancelada")],
        )
        view = VentasView()
        qtbot.addWidget(view)
        assert view._table.cellWidget(0, 6) is None

    def test_estado_rembolsada_se_muestra(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        _fake_session(
            mocker,
            rows=[_make_row(_make_sale(status_id=4), status="Rembolsada")],
        )
        view = VentasView()
        qtbot.addWidget(view)
        assert view._table.item(0, 5).text() == "Rembolsada"


# ── Refund flow ─────────────────────────────────────────────────────────


class TestRembolsarFlujo:
    """Tests for the _rembolsar flow."""

    def _con_sale_db(self, session_fake: MagicMock) -> None:
        detail = MagicMock()
        detail.quantity = 2
        detail.subtotal = Decimal("30.00")
        product = MagicMock()
        product.name = "Gafas Test"
        detail.product = product

        sale_db = MagicMock(spec=Sale)
        sale_db.invoice_number = "FAC-000001"
        sale_db.total = Decimal("60.00")
        sale_db.details = [detail]
        customer = MagicMock()
        customer.name = "Ana López"
        sale_db.customer = customer
        session_fake.get.return_value = sale_db

    def test_confirmacion_cancelada_no_llama_servicio(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        fake, _ = _fake_session(mocker, rows=[_make_row(_make_sale())])
        self._con_sale_db(fake)
        view = VentasView()
        qtbot.addWidget(view)
        mocker.patch(
            "opticamanager.ui.views.ventas_view.dialogo_confirmacion",
            return_value=False,
        )
        service = mocker.patch("opticamanager.ui.views.ventas_view.reembolsar_venta")
        view._rembolsar(_make_sale())
        service.assert_not_called()

    def test_rembolso_exitoso(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        fake, _ = _fake_session(mocker, rows=[_make_row(_make_sale())])
        self._con_sale_db(fake)
        view = VentasView()
        qtbot.addWidget(view)
        mocker.patch(
            "opticamanager.ui.views.ventas_view.dialogo_confirmacion",
            return_value=True,
        )
        service = mocker.patch(
            "opticamanager.ui.views.ventas_view.reembolsar_venta",
            return_value=MagicMock(),
        )
        info_msgs: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: info_msgs.append("ok"),
        )
        view._rembolsar(_make_sale())
        service.assert_called_once_with(sale_id=1, user_id=1)
        assert info_msgs

    def test_rembolso_error_servicio(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        fake, _ = _fake_session(mocker, rows=[_make_row(_make_sale())])
        self._con_sale_db(fake)
        view = VentasView()
        qtbot.addWidget(view)
        mocker.patch(
            "opticamanager.ui.views.ventas_view.dialogo_confirmacion",
            return_value=True,
        )
        mocker.patch(
            "opticamanager.ui.views.ventas_view.reembolsar_venta",
            side_effect=ValueError("La venta 'FAC-000001' ya fue rembolsada"),
        )
        errors: list[tuple] = []
        mocker.patch(
            "opticamanager.ui.views.ventas_view.dialogo_error",
            side_effect=lambda *_a, **_k: errors.append(_a),
        )
        view._rembolsar(_make_sale())
        assert errors
        assert "ya fue rembolsada" in errors[0][2]

    def test_rembolso_no_admin(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        fake, _ = _fake_session(mocker, rows=[_make_row(_make_sale())])
        self._con_sale_db(fake)
        view = VentasView()
        qtbot.addWidget(view)
        mocker.patch(
            "opticamanager.ui.views.ventas_view.dialogo_confirmacion",
            return_value=True,
        )
        mocker.patch(
            "opticamanager.ui.views.ventas_view.reembolsar_venta",
            side_effect=PermissionError(
                "Permiso denegado: se requiere el rol Admin y el usuario "
                "actual es 'Vendedor'"
            ),
        )
        errors: list[tuple] = []
        mocker.patch(
            "opticamanager.ui.views.ventas_view.dialogo_error",
            side_effect=lambda *_a, **_k: errors.append(_a),
        )
        view._rembolsar(_make_sale())
        assert errors
        assert "Permiso denegado" in errors[0][2]

    def test_rembolso_sin_sesion(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        fake, _ = _fake_session(mocker, rows=[_make_row(_make_sale())])
        self._con_sale_db(fake)
        view = VentasView()
        qtbot.addWidget(view)
        mocker.patch(
            "opticamanager.ui.views.ventas_view.dialogo_confirmacion",
            return_value=True,
        )
        critical_msgs: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "critical",
            side_effect=lambda *_a, **_k: critical_msgs.append("ok"),
        )
        view._rembolsar(_make_sale())
        assert critical_msgs
