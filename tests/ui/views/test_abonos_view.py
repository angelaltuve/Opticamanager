"""Tests for AbonosView and _AbonoDialog: pending sales and partial payments."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QMessageBox,
)
from pytest_mock import MockerFixture

from opticamanager.core.session import UserSession
from opticamanager.models.customer import Customer
from opticamanager.models.sale import Sale
from opticamanager.services.exchange_rate import RateInfo
from opticamanager.ui.views.abonos_view import (
    AbonosView,
    _AbonoDialog,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_sale(
    sale_id: int = 1,
    invoice: str = "FAC-000001",
    total: Decimal = Decimal("100.00"),
    status_id: int = 2,
) -> MagicMock:
    sale = MagicMock(spec=Sale)
    sale.id = sale_id
    sale.invoice_number = invoice
    sale.total = total
    sale.status_id = status_id
    sale.amount_received = None
    sale.created_at = datetime(2026, 9, 20)
    return sale


def _make_customer(name: str = "Ana López") -> MagicMock:
    cust = MagicMock(spec=Customer)
    cust.id = 1
    cust.name = name
    return cust


def _fake_session(mocker: MockerFixture, rows=None, payments=None):
    """Create a fake session that returns controlled query results."""
    fake = MagicMock()
    manager = mocker.patch("opticamanager.ui.views.abonos_view.SessionManager")
    manager.return_value.__enter__.return_value = fake
    manager.return_value.__exit__.return_value = False

    if rows is None:
        rows = []
    fake.exec.return_value.all.return_value = rows

    # Payment sum queries return 0 by default
    if payments is None:
        payments = {}
    fake.execute.return_value.scalar_one.return_value = 0
    return fake, manager


# ── _AbonoDialog Tests ────────────────────────────────────────────────


class TestAbonoDialog:
    """Tests for the partial payment dialog."""

    def test_creacion_dialog(self, qtbot: QtBot) -> None:
        sale = _make_sale()
        dlg = _AbonoDialog(sale, Decimal("100.00"))
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Abono — FAC-000001"
        assert dlg._monto_spin.value() == 100.00
        # PAYMENT_METHODS[0] is "Pago Móvil" (first item in combo)
        assert dlg._metodo_combo.currentText() == "Pago Móvil"
        # But internal default _metodo is "Efectivo Bs"
        assert dlg._metodo == "Efectivo Bs"

    def test_monto_property(self, qtbot: QtBot) -> None:
        sale = _make_sale()
        dlg = _AbonoDialog(sale, Decimal("50.00"))
        qtbot.addWidget(dlg)
        assert dlg.monto == Decimal("0")

    def test_metodo_property(self, qtbot: QtBot) -> None:
        sale = _make_sale()
        dlg = _AbonoDialog(sale, Decimal("50.00"))
        qtbot.addWidget(dlg)
        assert dlg.metodo == "Efectivo Bs"

    def test_validate_and_accept_exitoso(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        sale = _make_sale()
        dlg = _AbonoDialog(sale, Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._monto_spin.setValue(50.00)
        dlg._metodo_combo.setCurrentText("Pago Móvil")
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.monto == Decimal("50.00")
        assert dlg.metodo == "Pago Móvil"

    def test_validate_monto_cero_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        """The spinbox has min=0.01, so value<=0 is unreachable through the UI.
        Mock value() to cover the branch."""
        sale = _make_sale()
        dlg = _AbonoDialog(sale, Decimal("100.00"))
        qtbot.addWidget(dlg)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox, "warning", side_effect=lambda *_a, **_k: warned.append("ok")
        )
        mocker.patch.object(dlg._monto_spin, "value", return_value=0.0)
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_validate_monto_excesivo_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        """The spinbox has max=the pending total, so a larger value is unreachable
        through the UI. Mock value() to cover the branch."""
        sale = _make_sale()
        dlg = _AbonoDialog(sale, Decimal("100.00"))
        qtbot.addWidget(dlg)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox, "warning", side_effect=lambda *_a, **_k: warned.append("ok")
        )
        mocker.patch.object(dlg._monto_spin, "value", return_value=150.0)
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_cancel_dialog(self, qtbot: QtBot) -> None:
        sale = _make_sale()
        dlg = _AbonoDialog(sale, Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg.reject()
        assert dlg.result() == QDialog.DialogCode.Rejected

    def test_info_labels_contiene_datos_venta(self, qtbot: QtBot) -> None:
        sale = _make_sale(total=Decimal("200.00"))
        pendiente = Decimal("100.00")
        dlg = _AbonoDialog(sale, pendiente)
        qtbot.addWidget(dlg)
        # The info label is a child QLabel with rich text
        from PyQt6.QtWidgets import QLabel

        labels = dlg.findChildren(QLabel)
        info_label = None
        for lbl in labels:
            if "FAC-000001" in (lbl.text() or ""):
                info_label = lbl
                break
        assert info_label is not None
        assert "200" in info_label.text()

    def test_spinbox_rango_maximo_igual_pendiente(self, qtbot: QtBot) -> None:
        sale = _make_sale()
        pendiente = Decimal("75.00")
        dlg = _AbonoDialog(sale, pendiente)
        qtbot.addWidget(dlg)
        assert dlg._monto_spin.maximum() == 75.00


# ── AbonosView Tests ────────────────────────────────────────────────────


class TestAbonosViewCreacion:
    """Smoke tests for AbonosView creation and UI setup."""

    def test_creacion_basica(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker, rows=[])
        view = AbonosView()
        qtbot.addWidget(view)
        assert isinstance(view, AbonosView)

    def test_tabla_columnas(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker, rows=[])
        view = AbonosView()
        qtbot.addWidget(view)
        assert view._table.columnCount() == 7

    def test_summary_vacio(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker, rows=[])
        view = AbonosView()
        qtbot.addWidget(view)
        assert "0" in view._summary_label.text()

    def test_search_placeholder(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_session(mocker, rows=[])
        view = AbonosView()
        qtbot.addWidget(view)
        assert "cliente" in view._search_input.placeholderText().lower()


class TestAbonosViewCargaDatos:
    """Tests for _load_pendientes populating the table."""

    def test_carga_una_venta_pendiente(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        sale = _make_sale(total=Decimal("200.00"))
        _fake_session(mocker, rows=[(sale, "Juan Pérez")])
        view = AbonosView()
        qtbot.addWidget(view)
        assert view._table.rowCount() == 1
        assert view._table.item(0, 0).text() == "Juan Pérez"
        assert view._table.item(0, 1).text() == "FAC-000001"
        assert "200" in view._summary_label.text()

    def test_carga_varias_ventas(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        sales = [
            (_make_sale(1, "FAC-000001", Decimal("100.00")), "Ana López"),
            (_make_sale(2, "FAC-000002", Decimal("250.00")), "Carlos Ruiz"),
            (_make_sale(3, "FAC-000003", Decimal("50.00")), "María García"),
        ]
        _fake_session(mocker, rows=sales)
        view = AbonosView()
        qtbot.addWidget(view)
        assert view._table.rowCount() == 3

    def test_venta_pendiente_con_pago_parcial(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        sale = _make_sale(total=Decimal("200.00"))
        fake, _ = _fake_session(mocker, rows=[(sale, "Juan Pérez")])
        # exec() returns rows; execute() returns payment sum = 50
        fake.exec.return_value.all.return_value = [(sale, "Juan Pérez")]
        fake.execute.return_value.scalar_one.return_value = Decimal("50.00")
        view = AbonosView()
        qtbot.addWidget(view)
        # Check pending amount shows 150 (200 - 50)
        assert view._table.rowCount() == 1
        pending_item = view._table.item(0, 5)
        assert pending_item is not None
        assert "150" in pending_item.text()

    def test_pendiente_negativo_se_ajusta_a_cero(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        """When payments exceed total, pending should show Bs. 0,00."""
        sale = _make_sale(total=Decimal("50.00"))
        fake, _ = _fake_session(mocker, rows=[(sale, "Cliente X")])
        # exec() returns rows; execute() returns payment sum = 75 (exceeds total)
        fake.exec.return_value.all.return_value = [(sale, "Cliente X")]
        fake.execute.return_value.scalar_one.return_value = Decimal("75.00")
        view = AbonosView()
        qtbot.addWidget(view)
        assert view._table.rowCount() == 1
        pending_item = view._table.item(0, 5)
        assert pending_item is not None
        assert "0" in pending_item.text()


class TestAbonosViewBusqueda:
    """Tests for search filtering."""

    def test_filtro_por_nombre(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [
            (_make_sale(1, "FAC-000001"), "Ana López"),
            (_make_sale(2, "FAC-000002"), "Carlos Ruiz"),
            (_make_sale(3, "FAC-000003"), "Ana García"),
        ]
        _fake_session(mocker, rows=rows)
        view = AbonosView()
        qtbot.addWidget(view)
        assert view._table.rowCount() == 3
        view._search_input.setText("Ana")
        assert view._table.rowCount() == 2

    def test_filtro_sin_resultados(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [
            (_make_sale(1, "FAC-000001"), "Ana López"),
        ]
        _fake_session(mocker, rows=rows)
        view = AbonosView()
        qtbot.addWidget(view)
        view._search_input.setText("ZZZZ")
        assert view._table.rowCount() == 0

    def test_filtro_case_insensitive(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        rows = [
            (_make_sale(1, "FAC-000001"), "Ana López"),
        ]
        _fake_session(mocker, rows=rows)
        view = AbonosView()
        qtbot.addWidget(view)
        view._search_input.setText("ana")
        assert view._table.rowCount() == 1


class TestAbonosViewBotonActualizar:
    """Tests for the refresh button."""

    def test_boton_actualizar_recarga(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        rows = [(_make_sale(1, "FAC-000001"), "Cliente")]
        _fake_session(mocker, rows=rows)
        view = AbonosView()
        qtbot.addWidget(view)
        # Change data and click refresh
        from PyQt6.QtWidgets import QPushButton

        btn_refresh = view.findChild(QPushButton, "")
        # Find by text
        for btn in view.findChildren(QPushButton):
            if "Actualizar" in btn.text():
                btn_refresh = btn
                break
        assert btn_refresh is not None
        _fake_session(mocker, rows=[])
        qtbot.mouseClick(btn_refresh, Qt.MouseButton.LeftButton)
        assert view._table.rowCount() == 0


class TestAbonarFlujo:
    """Tests for the _abonar payment flow."""

    def test_abonar_dialog_cancelado_no_hace_nada(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        sale = _make_sale(total=Decimal("100.00"))
        _fake_session(mocker, rows=[(sale, "Juan")])
        view = AbonosView()
        qtbot.addWidget(view)
        # Mock _AbonoDialog to return Rejected
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.abonos_view._AbonoDialog",
            return_value=mock_dlg,
        )
        view._abonar(sale, Decimal("100.00"))
        # No commit should happen
        mock_dlg.exec.assert_called_once()

    def test_abonar_sin_sesion_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        sale = _make_sale(total=Decimal("100.00"))
        _fake_session(mocker, rows=[])
        view = AbonosView()
        qtbot.addWidget(view)
        # Mock dialog to accept
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.monto = Decimal("50.00")
        mock_dlg.metodo = "Efectivo Bs"
        mocker.patch(
            "opticamanager.ui.views.abonos_view._AbonoDialog",
            return_value=mock_dlg,
        )
        # Clear user session
        UserSession._user = None
        critical_msgs: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "critical",
            side_effect=lambda *_a, **_k: critical_msgs.append("ok"),
        )
        view._abonar(sale, Decimal("100.00"))
        assert critical_msgs

    def test_abonar_venta_no_encontrada(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        sale = _make_sale(sale_id=999, total=Decimal("100.00"))
        _fake_session(mocker, rows=[])
        view = AbonosView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.monto = Decimal("50.00")
        mock_dlg.metodo = "Efectivo Bs"
        mocker.patch(
            "opticamanager.ui.views.abonos_view._AbonoDialog",
            return_value=mock_dlg,
        )
        mocker.patch(
            "opticamanager.ui.views.abonos_view.get_rate_info",
            return_value=RateInfo(rate=Decimal("36.00"), source="bcv", updated_at=None),
        )
        # Session.get returns None for the sale
        fake, _ = _fake_session(mocker, rows=[])
        fake.get.return_value = None
        critical_msgs: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "critical",
            side_effect=lambda *_a, **_k: critical_msgs.append("ok"),
        )
        view._abonar(sale, Decimal("100.00"))
        assert critical_msgs

    def test_abonar_pago_bs_exitoso(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        sale = _make_sale(total=Decimal("100.00"))
        _fake_session(mocker, rows=[(sale, "Juan")])
        view = AbonosView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.monto = Decimal("50.00")
        mock_dlg.metodo = "Efectivo Bs"
        mocker.patch(
            "opticamanager.ui.views.abonos_view._AbonoDialog",
            return_value=mock_dlg,
        )
        mocker.patch(
            "opticamanager.ui.views.abonos_view.get_rate_info",
            return_value=RateInfo(rate=Decimal("36.00"), source="bcv", updated_at=None),
        )
        fake_sale = MagicMock()
        fake_sale.id = sale.id
        fake_sale.total = sale.total
        fake_sale.invoice_number = sale.invoice_number
        fake_sale.amount_received = Decimal("0")
        fake, manager = _fake_session(mocker, rows=[])
        fake.get.return_value = fake_sale
        # Return existing payments sum = 0, then total_paid sum = 0
        fake.execute.return_value.scalar_one.return_value = Decimal("0")
        info_msgs: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: info_msgs.append("ok"),
        )
        view._abonar(sale, Decimal("100.00"))
        fake.add.assert_called_once()
        fake_sale.amount_received = Decimal("50.00")
        assert info_msgs
        fake.commit.assert_called()

    def test_abonar_pago_usd_con_rate(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        sale = _make_sale(total=Decimal("360.00"))
        _fake_session(mocker, rows=[(sale, "Juan")])
        view = AbonosView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.monto = Decimal("10.00")
        mock_dlg.metodo = "Efectivo Dólares"
        mocker.patch(
            "opticamanager.ui.views.abonos_view._AbonoDialog",
            return_value=mock_dlg,
        )
        mocker.patch(
            "opticamanager.ui.views.abonos_view.get_rate_info",
            return_value=RateInfo(rate=Decimal("36.00"), source="bcv", updated_at=None),
        )
        fake_sale = MagicMock()
        fake_sale.id = sale.id
        fake_sale.total = sale.total
        fake_sale.invoice_number = sale.invoice_number
        fake_sale.amount_received = Decimal("0")
        fake, _ = _fake_session(mocker, rows=[])
        fake.get.return_value = fake_sale
        fake.execute.return_value.scalar_one.return_value = Decimal("0")
        info_msgs: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: info_msgs.append("ok"),
        )
        view._abonar(sale, Decimal("360.00"))
        # Verify a payment was added with USD currency
        added_payment = fake.add.call_args_list[0][0][0]
        assert added_payment.currency == "USD"
        assert added_payment.amount == Decimal("10.00")
        assert added_payment.amount_bs == Decimal("360.00")
        assert added_payment.rate_used == Decimal("36.00")
        assert info_msgs

    def test_abonar_completa_venta_cuando_saldo_cero(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        """When total_paid >= total, sale status changes to 1 (Completada)."""
        sale = _make_sale(total=Decimal("50.00"))
        _fake_session(mocker, rows=[(sale, "Juan")])
        view = AbonosView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.monto = Decimal("50.00")
        mock_dlg.metodo = "Efectivo Bs"
        mocker.patch(
            "opticamanager.ui.views.abonos_view._AbonoDialog",
            return_value=mock_dlg,
        )
        mocker.patch(
            "opticamanager.ui.views.abonos_view.get_rate_info",
            return_value=RateInfo(rate=Decimal("36.00"), source="bcv", updated_at=None),
        )
        fake_sale = MagicMock()
        fake_sale.id = sale.id
        fake_sale.total = sale.total
        fake_sale.invoice_number = sale.invoice_number
        fake_sale.amount_received = Decimal("0")
        fake, _ = _fake_session(mocker, rows=[])
        fake.get.return_value = fake_sale
        # Return existing payments sum = 0, then total_paid = 50 after adding
        fake.execute.return_value.scalar_one.return_value = Decimal("0")
        info_calls: list[tuple] = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *args, **kwargs: info_calls.append(args),
        )
        view._abonar(sale, Decimal("50.00"))
        assert fake_sale.status_id == 1
        # The information dialog should be called (with "saldada" in the message)
        assert len(info_calls) >= 1

    def test_abonar_nuevo_pendiente_negativo_se_ajusta_a_cero(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        """When total_paid exceeds total, nuevo_pendiente is clamped to 0."""
        sale = _make_sale(total=Decimal("50.00"))
        _fake_session(mocker, rows=[(sale, "Juan")])
        view = AbonosView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.monto = Decimal("30.00")
        mock_dlg.metodo = "Efectivo Bs"
        mocker.patch(
            "opticamanager.ui.views.abonos_view._AbonoDialog",
            return_value=mock_dlg,
        )
        mocker.patch(
            "opticamanager.ui.views.abonos_view.get_rate_info",
            return_value=RateInfo(rate=Decimal("36.00"), source="bcv", updated_at=None),
        )
        fake_sale = MagicMock()
        fake_sale.id = sale.id
        fake_sale.total = sale.total
        fake_sale.invoice_number = sale.invoice_number
        fake_sale.amount_received = Decimal("0")
        fake, _ = _fake_session(mocker, rows=[])
        fake.get.return_value = fake_sale
        # Existing payments sum = 30, plus current 30 = 60 > total 50
        fake.execute.return_value.scalar_one.return_value = Decimal("30.00")
        info_calls: list[tuple] = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *args, **kwargs: info_calls.append(args),
        )
        view._abonar(sale, Decimal("50.00"))
        # total_paid = 30 + 30 = 60 > 50, nuevo_pendiente clamped to 0
        assert fake_sale.status_id == 1  # Completada
        assert len(info_calls) >= 1

    def test_abonar_sin_rate_usd_monto_se_usa_directo(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        """When rate is None/0 and method is USD, amount_bs = monto."""
        sale = _make_sale(total=Decimal("100.00"))
        _fake_session(mocker, rows=[(sale, "Juan")])
        view = AbonosView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.monto = Decimal("10.00")
        mock_dlg.metodo = "Efectivo Dólares"
        mocker.patch(
            "opticamanager.ui.views.abonos_view._AbonoDialog",
            return_value=mock_dlg,
        )
        mocker.patch(
            "opticamanager.ui.views.abonos_view.get_rate_info",
            return_value=RateInfo(rate=Decimal("0"), source="unknown", updated_at=None),
        )
        fake_sale = MagicMock()
        fake_sale.id = sale.id
        fake_sale.total = sale.total
        fake_sale.invoice_number = sale.invoice_number
        fake_sale.amount_received = Decimal("0")
        fake, _ = _fake_session(mocker, rows=[])
        fake.get.return_value = fake_sale
        fake.execute.return_value.scalar_one.return_value = Decimal("0")
        info_msgs: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: info_msgs.append("ok"),
        )
        view._abonar(sale, Decimal("100.00"))
        added_payment = fake.add.call_args_list[0][0][0]
        assert added_payment.amount_bs == Decimal("10.00")
        assert added_payment.rate_used is None


class TestAbonosViewMetadataTabla:
    """Tests for table metadata: dates, alignment, editable flags."""

    def test_fecha_venta_en_tabla(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        sale = _make_sale()
        sale.created_at = datetime(2025, 12, 25)
        _fake_session(mocker, rows=[(sale, "Cliente")])
        view = AbonosView()
        qtbot.addWidget(view)
        date_item = view._table.item(0, 2)
        assert date_item is not None
        assert "25/12/2025" in date_item.text()

    def test_fecha_none_muestra_guion(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        sale = _make_sale()
        sale.created_at = None
        _fake_session(mocker, rows=[(sale, "Cliente")])
        view = AbonosView()
        qtbot.addWidget(view)
        date_item = view._table.item(0, 2)
        assert date_item is not None
        assert date_item.text() == "—"

    def test_celdas_no_editables(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        sale = _make_sale()
        _fake_session(mocker, rows=[(sale, "Cliente")])
        view = AbonosView()
        qtbot.addWidget(view)
        for col in range(6):
            item = view._table.item(0, col)
            if item is not None:
                assert not (item.flags() & Qt.ItemFlag.ItemIsEditable)

    def test_boton_abonar_en_columna_6(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        sale = _make_sale()
        _fake_session(mocker, rows=[(sale, "Cliente")])
        view = AbonosView()
        qtbot.addWidget(view)
        from PyQt6.QtWidgets import QPushButton

        btn_widget = view._table.cellWidget(0, 6)
        assert btn_widget is not None
        btns = btn_widget.findChildren(QPushButton)
        assert len(btns) == 1
        assert "Abonar" in btns[0].text()

    def test_boton_abonar_abre_dialog(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        sale = _make_sale(total=Decimal("100.00"))
        _fake_session(mocker, rows=[(sale, "Cliente")])
        view = AbonosView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.abonos_view._AbonoDialog",
            return_value=mock_dlg,
        )
        from PyQt6.QtWidgets import QPushButton

        btn_widget = view._table.cellWidget(0, 6)
        btn = btn_widget.findChildren(QPushButton)[0]
        qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
        mock_dlg.exec.assert_called_once()
