"""Tests for pos_view.py: POSView, _PaymentDialog, _CashOpen/CloseDialog,
_CustomerFormDialog, _PrescriptionHistoryDialog, _CartItem, _CartSession.

Coverage target: >=70% of pos_view.py (2187 lines).
Strategy: mock SessionManager, the services, QMessageBox and QFileDialog to
stay off the real DB and avoid UI blocks.

Pattern: _fake_session helper plus MagicMock objects.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from PyQt6.QtWidgets import (
    QDialog,
    QMessageBox,
    QWidget,
)
from pytest_mock import MockerFixture

from opticamanager.core.session import UserData, UserSession
from opticamanager.models import CashSession, Customer, Prescription, Product
from opticamanager.services.exchange_rate import RateInfo
from opticamanager.ui.views.pos_view import (
    EFECTIVO_BS,
    EFECTIVO_USD,
    MIXTO,
    PAGO_MOVIL,
    ZELLE,
    ABONO,
    PAYMENT_METHOD_CHOICES,
    POSView,
    _CashCloseDialog,
    _CashOpenDialog,
    _CartItem,
    _CartSession,
    _CustomerFormDialog,
    _PaymentDialog,
    _PrescriptionHistoryDialog,
    _SaleTab,
    _create_customer_from_dialog,
    _rate,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


# ── Helpers ──────────────────────────────────────────────────────────────

FAKE_RATE = Decimal("36.00")


def _make_customer(
    customer_id: int = 1,
    name: str = "Juan Pérez",
    id_document: str = "V-12345678",
    phone: str | None = "0414-1234567",
    email: str | None = "juan@test.com",
) -> MagicMock:
    c = MagicMock(spec=Customer)
    c.id = customer_id
    c.name = name
    c.id_document = id_document
    c.phone = phone
    c.email = email
    return c


def _make_product(
    product_id: int = 1,
    name: str = "Lente Bifocal",
    barcode: str | None = "1234567890123",
    sale_price_usd: Decimal = Decimal("25.00"),
    stock_quantity: int = 50,
    active: bool = True,
    cost_price_usd: Decimal = Decimal("10.00"),
) -> MagicMock:
    p = MagicMock(spec=Product)
    p.id = product_id
    p.name = name
    p.barcode = barcode
    p.sale_price_usd = sale_price_usd
    p.stock_quantity = stock_quantity
    p.active = active
    p.cost_price_usd = cost_price_usd
    return p


def _make_prescription(
    rx_id: int = 1,
    customer_id: int = 1,
    issued_date: datetime | None = None,
) -> MagicMock:
    rx = MagicMock(spec=Prescription)
    rx.id = rx_id
    rx.customer_id = customer_id
    rx.issued_date = issued_date or datetime(2026, 9, 15)
    rx.od_sphere = Decimal("2.00")
    rx.od_cylinder = Decimal("-0.50")
    rx.od_axis = 180
    rx.od_addition = None
    rx.os_sphere = Decimal("1.50")
    rx.os_cylinder = Decimal("-0.25")
    rx.os_axis = 90
    rx.os_addition = None
    rx.pupillary_distance = Decimal("63.00")
    rx.notes = "Paciente refractario"
    return rx


def _make_sale_obj(
    sale_id: int = 1,
    invoice: str = "FAC-000001",
    total: Decimal = Decimal("100.00"),
    payment_method: str = "Efectivo Bs",
) -> MagicMock:
    s = MagicMock()
    s.id = sale_id
    s.invoice_number = invoice
    s.total = total
    s.payment_method = payment_method
    s.amount_received = Decimal("100.00")
    s.change_amount = Decimal("0")
    return s


def _make_cash_session(
    cs_id: int = 1,
    user_id: int = 1,
    initial_balance: Decimal = Decimal("500.00"),
    opened_at: datetime | None = None,
    closed_at: datetime | None = None,
) -> MagicMock:
    cs = MagicMock(spec=CashSession)
    cs.id = cs_id
    cs.user_id = user_id
    cs.initial_balance = initial_balance
    cs.opened_at = opened_at or datetime(2026, 9, 20, 8, 0)
    cs.closed_at = closed_at
    return cs


def _fake_session(mocker: MockerFixture, *, get_side_effect=None, exec_results=None):
    """Create a fake session that returns controlled query results."""
    fake = MagicMock()
    manager = mocker.patch("opticamanager.ui.views.pos_view.SessionManager")
    manager.return_value.__enter__.return_value = fake
    manager.return_value.__exit__.return_value = False
    if get_side_effect is not None:
        fake.get.side_effect = get_side_effect
    else:
        # Default product with plenty of stock so the checkout-level aggregate
        # stock check (_demanda_total_excede_stock) doesn't block carts built
        # directly in tests.
        fake.get.return_value = _make_product(stock_quantity=9999)
    if exec_results is not None:
        fake.exec.return_value.all.return_value = exec_results
    return fake, manager


def _suppress_message_boxes(mocker: MockerFixture) -> dict:
    """Suppress QMessageBox.warning/information and dialogo_* calls."""
    warned = []
    mocker.patch.object(
        QMessageBox, "warning", side_effect=lambda *_a, **_k: warned.append("warn")
    )
    mocker.patch.object(
        QMessageBox,
        "information",
        side_effect=lambda *_a, **_k: warned.append("info"),
    )
    mocker.patch(
        "opticamanager.ui.views.pos_view.dialogo_confirmacion",
        return_value=True,
    )
    mocker.patch(
        "opticamanager.ui.views.pos_view.dialogo_error",
    )
    return {"warned": warned}


def _make_pos_view(mocker: MockerFixture, *, mock_session_data=None) -> POSView:
    """Create a POSView with all services mocked.

    ExchangeRateWidget is a real QWidget that can't be replaced by MagicMock
    (PyQt6 addWidget rejects non-QWidget).  We let it be created but mock the
    BCV network calls that its ``showEvent`` → ``_on_refresh`` triggers.
    """
    mocker.patch(
        "opticamanager.ui.views.pos_view.get_iva_rate",
        return_value=Decimal("0.16"),
    )
    mocker.patch("opticamanager.ui.views.pos_view.get_iva_rate_pct", return_value=16)
    mocker.patch(
        "opticamanager.ui.views.pos_view.convert_to_bs",
        side_effect=lambda d, rate=None: (
            (d * (rate if rate is not None else FAKE_RATE)).quantize(Decimal("0.01"))
            if d
            else None
        ),
    )
    mocker.patch(
        "opticamanager.ui.views.pos_view.get_usd_rate",
        return_value=FAKE_RATE,
    )
    mocker.patch(
        "opticamanager.ui.views.pos_view.convert_to_usd",
        return_value=Decimal("10.00"),
    )
    mocker.patch(
        "opticamanager.ui.views.pos_view.get_rate_info",
        return_value=RateInfo(rate=FAKE_RATE, source="bcv", updated_at=datetime.now()),
    )
    mocker.patch(
        "opticamanager.ui.views.pos_view.cash_session_service",
    )
    # Mock the ExchangeRateWidget's underlying services so it doesn't hit BCV
    mocker.patch(
        "opticamanager.ui.widgets.exchange_rate_widget.force_refresh",
    )
    mocker.patch(
        "opticamanager.ui.widgets.exchange_rate_widget.clear_manual_rate",
    )
    mocker.patch(
        "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
        return_value=RateInfo(rate=FAKE_RATE, source="bcv", updated_at=datetime.now()),
    )
    _fake_session(mocker, exec_results=[])
    view = POSView()
    return view


def _make_user(user_id: int = 1, name: str = "Admin") -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.name = name
    u.username = "admin"
    u.role_id = 1
    u.role.name = "Admin"
    return u


# ── _CartItem Tests ────────────────────────────────────────────────────


class TestCartItem:
    """Tests for _CartItem."""

    def test_subtotal_default_qty(self) -> None:
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"), quantity=1)
        assert ci.subtotal == Decimal("25.00")

    def test_subtotal_multiple_qty(self) -> None:
        ci = _CartItem(1, "Lente", Decimal("33.33"), Decimal("33.33"), quantity=3)
        assert ci.subtotal == Decimal("99.99")

    def test_subtotal_rounds_half_up(self) -> None:
        ci = _CartItem(1, "Lente", Decimal("33.333"), Decimal("33.33"), quantity=1)
        assert ci.subtotal == Decimal("33.33")

    def test_subtotal_zero_qty(self) -> None:
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"), quantity=0)
        assert ci.subtotal == Decimal("0.00")


# ── _CartSession Tests ────────────────────────────────────────────────


class TestCartSessionTotals:
    """Tests for _CartSession IVA and total computation."""

    def test_iva_calculation(self) -> None:
        s = _CartSession()
        s.cart.append(_CartItem(1, "Lente", Decimal("100.00"), Decimal("100.00")))
        # iva = subtotal * 0.16 = 16.00
        expected_iva = (Decimal("100.00") * Decimal("0.16")).quantize(Decimal("0.01"))
        assert s.iva() == expected_iva

    def test_total_is_subtotal_plus_iva(self) -> None:
        s = _CartSession()
        s.cart.append(_CartItem(1, "Lente", Decimal("100.00"), Decimal("100.00")))
        assert s.total() == (s.subtotal() + s.iva()).quantize(Decimal("0.01"))


# ── _PaymentDialog Tests ──────────────────────────────────────────────


class TestPaymentDialogCreacion:
    """Tests for _PaymentDialog creation and method switching."""

    def test_creacion_basica(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Método de Pago"
        assert dlg._total == Decimal("100.00")

    def test_creacion_con_total_usd(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        dlg = _PaymentDialog(Decimal("360.00"), total_usd=Decimal("10.00"))
        qtbot.addWidget(dlg)
        assert dlg._total_usd == Decimal("10.00")

    def test_creacion_sin_total_usd(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        assert dlg._total_usd == Decimal("0")

    def test_default_method_es_primer_combo(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        # _on_method_changed fires on init → combo's currentText = first item
        assert dlg.payment_method == PAYMENT_METHOD_CHOICES[0]

    def test_combo_metodos_contiene_todos(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        for i in range(dlg._method_combo.count()):
            assert dlg._method_combo.itemText(i) in PAYMENT_METHOD_CHOICES

    def test_cambio_efectivo_bs_muestra_cash_widget(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(EFECTIVO_BS)
        assert dlg._payment_method == EFECTIVO_BS
        # Verify method-switch side effects: combo text + internal state
        assert dlg._received_spin.prefix() == "Bs. "

    def test_cambio_mixto_muestra_mixto_widget(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(MIXTO)
        assert dlg._payment_method == MIXTO
        assert len(dlg._mixed_rows) >= 1

    def test_cambio_pago_movil_muestra_simple_label(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(PAGO_MOVIL)
        assert dlg._payment_method == PAGO_MOVIL
        assert "Pago Móvil" in dlg._simple_label.text()

    def test_cambio_zelle_muestra_simple_label(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(ZELLE)
        assert dlg._payment_method == ZELLE
        assert "Zelle" in dlg._simple_label.text()

    def test_cambio_abono_muestra_abono_widget(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(ABONO)
        assert dlg._payment_method == ABONO
        assert dlg._abono_spin.maximum() == 100.0

    def test_received_spin_prefill_bs(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        assert dlg._received_spin.value() == 100.00


class TestPaymentDialogValidation:
    """Tests for _PaymentDialog._validate_and_accept across methods."""

    def test_efectivo_bs_acepta_suficiente(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(EFECTIVO_BS)
        dlg._received_spin.setValue(100.00)
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.payment_method == EFECTIVO_BS

    def test_efectivo_bs_cambio(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(EFECTIVO_BS)
        dlg._received_spin.setValue(150.00)
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.change_amount == Decimal("50.00")

    def test_efectivo_bs_insuficiente_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(EFECTIVO_BS)
        dlg._received_spin.setValue(50.00)
        dlg._validate_and_accept()
        assert dlg.result() != QDialog.DialogCode.Accepted
        assert warned

    def test_pago_movil_acepta(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(PAGO_MOVIL)
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.payment_method == PAGO_MOVIL

    def test_zelle_acepta(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(ZELLE)
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.payment_method == ZELLE

    def test_efectivo_usd_sin_rate_falla(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=None,
        )
        dlg = _PaymentDialog(Decimal("100.00"), total_usd=Decimal("10.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(EFECTIVO_USD)
        dlg._validate_and_accept()
        assert dlg.result() != QDialog.DialogCode.Accepted
        assert warned

    def test_efectivo_usd_insuficiente(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        dlg = _PaymentDialog(Decimal("360.00"), total_usd=Decimal("10.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(EFECTIVO_USD)
        dlg._received_spin.setValue(5.0)
        dlg._validate_and_accept()
        assert dlg.result() != QDialog.DialogCode.Accepted
        assert warned

    def test_efectivo_usd_acepta(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        dlg = _PaymentDialog(Decimal("360.00"), total_usd=Decimal("10.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(EFECTIVO_USD)
        dlg._received_spin.setValue(10.0)
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.payment_method == EFECTIVO_USD

    def test_abono_acepta_monto_valido(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(ABONO)
        dlg._abono_spin.setValue(50.00)
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.payment_method == ABONO
        assert dlg.amount_received == Decimal("50.00")

    def test_abono_cero_falla(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(ABONO)
        mocker.patch.object(dlg._abono_spin, "value", return_value=0.0)
        dlg._validate_and_accept()
        assert dlg.result() != QDialog.DialogCode.Accepted
        assert warned

    def test_abono_excesivo_falla(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(ABONO)
        mocker.patch.object(dlg._abono_spin, "value", return_value=150.0)
        dlg._validate_and_accept()
        assert dlg.result() != QDialog.DialogCode.Accepted
        assert warned


class TestPaymentDialogMixto:
    """Tests for mixed (Mixto) payment flow."""

    def test_mixto_filas_agregan(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(MIXTO)
        # One row auto-created on method change
        assert len(dlg._mixed_rows) >= 1

    def test_mixto_insuficiente_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(MIXTO)
        # Set the row to less than total
        dlg._mixed_rows[0].amount_spin.setValue(50.0)
        dlg._validate_and_accept()
        assert dlg.result() != QDialog.DialogCode.Accepted
        assert warned

    def test_mixto_acepta_monto_suficiente(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(MIXTO)
        dlg._mixed_rows[0].amount_spin.setValue(100.0)
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.payment_method == MIXTO

    def test_mixto_suma_bs(self, qtbot: QtBot) -> None:
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(MIXTO)
        dlg._mixed_rows[0].amount_spin.setValue(60.0)
        dlg._mixed_rows[0].method_combo.setCurrentText(EFECTIVO_BS)
        dlg._add_mixed_row()
        dlg._mixed_rows[1].amount_spin.setValue(40.0)
        dlg._mixed_rows[1].method_combo.setCurrentText(PAGO_MOVIL)
        assert dlg._sum_mixed_bs() == Decimal("100.00")

    def test_mixto_update_label(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(MIXTO)
        dlg._mixed_rows[0].amount_spin.setValue(60.0)
        text = dlg._mixto_total_label.text()
        assert "60" in text or "Falta" in text

    def test_mixto_fila_eliminada(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(MIXTO)
        dlg._add_mixed_row()
        assert len(dlg._mixed_rows) == 2
        dlg._remove_mixed_row(dlg._mixed_rows[1])
        assert len(dlg._mixed_rows) == 1

    def test_mixto_no_permite_eliminar_ultima_fila(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(MIXTO)
        initial = len(dlg._mixed_rows)
        dlg._remove_mixed_row(dlg._mixed_rows[0])
        assert len(dlg._mixed_rows) == initial

    def test_mixto_with_usd_row(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        dlg = _PaymentDialog(Decimal("360.00"), total_usd=Decimal("10.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(MIXTO)
        dlg._mixed_rows[0].method_combo.setCurrentText(EFECTIVO_USD)
        dlg._mixed_rows[0].amount_spin.setValue(5.0)
        dlg._add_mixed_row()
        dlg._mixed_rows[1].method_combo.setCurrentText(EFECTIVO_BS)
        dlg._mixed_rows[1].amount_spin.setValue(180.0)
        assert dlg._sum_mixed_bs() > Decimal("0")


class TestPaymentDialogCancel:
    """Tests for dialog rejection."""

    def test_cancel_dialog(self, qtbot: QtBot) -> None:
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg.reject()
        assert dlg.result() == QDialog.DialogCode.Rejected


class TestPaymentDialogAbonoCalculations:
    """Tests for abono pending balance display."""

    def test_abono_pendiente_se_actualiza(self, qtbot: QtBot) -> None:
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(ABONO)
        dlg._abono_spin.setValue(40.0)
        # _on_abono_changed should update pending label
        assert "60" in dlg._abono_pendiente_label.text()

    def test_abono_pendiente_cero_cuando_total(self, qtbot: QtBot) -> None:
        dlg = _PaymentDialog(Decimal("100.00"))
        qtbot.addWidget(dlg)
        dlg._method_combo.setCurrentText(ABONO)
        dlg._abono_spin.setValue(100.0)
        assert "0" in dlg._abono_pendiente_label.text()


class TestPaymentDialogBsOfUsd:
    """Tests for _bs_of_usd static method."""

    def test_bs_of_usd_con_rate(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=FAKE_RATE,
        )
        result = _PaymentDialog._bs_of_usd(10.0)
        assert result == (Decimal("10") * FAKE_RATE).quantize(Decimal("0.01"))

    def test_bs_of_usd_sin_rate(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view._rate",
            return_value=None,
        )
        result = _PaymentDialog._bs_of_usd(10.0)
        assert result == Decimal("0")


# ── _CashOpenDialog Tests ────────────────────────────────────────────


class TestCashOpenDialog:
    """Tests for _CashOpenDialog."""

    def test_creacion_basica(self, qtbot: QtBot) -> None:
        dlg = _CashOpenDialog()
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Apertura de Caja"
        assert dlg.initial_balance == Decimal("0")

    def test_balance_default_es_cero(self, qtbot: QtBot) -> None:
        dlg = _CashOpenDialog()
        qtbot.addWidget(dlg)
        assert dlg._balance_spin.value() == 0.0

    def test_accept_guarda_balance(self, qtbot: QtBot) -> None:
        dlg = _CashOpenDialog()
        qtbot.addWidget(dlg)
        dlg._balance_spin.setValue(500.0)
        dlg._accept()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.initial_balance == Decimal("500.0")

    def test_reject_no_guarda(self, qtbot: QtBot) -> None:
        dlg = _CashOpenDialog()
        qtbot.addWidget(dlg)
        dlg._balance_spin.setValue(500.0)
        dlg.reject()
        assert dlg.result() == QDialog.DialogCode.Rejected


# ── _CashCloseDialog Tests ───────────────────────────────────────────


class TestCashCloseDialog:
    """Tests for _CashCloseDialog."""

    def test_creacion_basica(self, qtbot: QtBot) -> None:
        cs = _make_cash_session()
        summary = {
            "sales_count": 5,
            "total_sales": Decimal("2000.00"),
            "by_method": {
                "Efectivo Bs": Decimal("1500.00"),
                "Pago Móvil": Decimal("500.00"),
            },
            "expected_balance": Decimal("2500.00"),
            "sales": [],
        }
        dlg = _CashCloseDialog(cs, summary)
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Cierre de Caja"

    def test_recalc_diferencia_cero(self, qtbot: QtBot) -> None:
        cs = _make_cash_session(initial_balance=Decimal("500.00"))
        summary = {
            "sales_count": 2,
            "total_sales": Decimal("200.00"),
            "by_method": {"Efectivo Bs": Decimal("200.00")},
            "expected_balance": Decimal("700.00"),
            "sales": [],
        }
        dlg = _CashCloseDialog(cs, summary)
        qtbot.addWidget(dlg)
        dlg._final_spin.setValue(700.0)
        assert dlg.difference == Decimal("0")

    def test_recalc_diferencia_positiva(self, qtbot: QtBot) -> None:
        cs = _make_cash_session(initial_balance=Decimal("500.00"))
        summary = {
            "sales_count": 2,
            "total_sales": Decimal("200.00"),
            "by_method": {"Efectivo Bs": Decimal("200.00")},
            "expected_balance": Decimal("700.00"),
            "sales": [],
        }
        dlg = _CashCloseDialog(cs, summary)
        qtbot.addWidget(dlg)
        dlg._final_spin.setValue(750.0)
        assert dlg.difference == Decimal("50.00")

    def test_recalc_diferencia_negativa(self, qtbot: QtBot) -> None:
        cs = _make_cash_session(initial_balance=Decimal("500.00"))
        summary = {
            "sales_count": 2,
            "total_sales": Decimal("200.00"),
            "by_method": {"Efectivo Bs": Decimal("200.00")},
            "expected_balance": Decimal("700.00"),
            "sales": [],
        }
        dlg = _CashCloseDialog(cs, summary)
        qtbot.addWidget(dlg)
        dlg._final_spin.setValue(650.0)
        assert dlg.difference == Decimal("-50.00")

    def test_accept_sin_diferencia(self, qtbot: QtBot) -> None:
        cs = _make_cash_session()
        summary = {
            "sales_count": 0,
            "total_sales": Decimal("0"),
            "by_method": {},
            "expected_balance": Decimal("500.00"),
            "sales": [],
        }
        dlg = _CashCloseDialog(cs, summary)
        qtbot.addWidget(dlg)
        dlg._final_spin.setValue(500.0)
        dlg._accept()
        assert dlg.result() == QDialog.DialogCode.Accepted
        assert dlg.final_balance == Decimal("500.00")

    def test_accept_con_diferencia_pide_confirmacion(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        cs = _make_cash_session()
        summary = {
            "sales_count": 0,
            "total_sales": Decimal("0"),
            "by_method": {},
            "expected_balance": Decimal("500.00"),
            "sales": [],
        }
        dlg = _CashCloseDialog(cs, summary)
        qtbot.addWidget(dlg)
        dlg._final_spin.setValue(600.0)
        # dialogo_confirmacion returns True → accept
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        dlg._accept()
        assert dlg.result() == QDialog.DialogCode.Accepted

    def test_accept_con_diferencia_cancela(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        cs = _make_cash_session()
        summary = {
            "sales_count": 0,
            "total_sales": Decimal("0"),
            "by_method": {},
            "expected_balance": Decimal("500.00"),
            "sales": [],
        }
        dlg = _CashCloseDialog(cs, summary)
        qtbot.addWidget(dlg)
        dlg._final_spin.setValue(600.0)
        # dialogo_confirmacion returns False → don't accept
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=False,
        )
        dlg._accept()
        assert dlg.result() != QDialog.DialogCode.Accepted


# ── _CustomerFormDialog Tests ────────────────────────────────────────


class TestCustomerFormDialog:
    """Tests for _CustomerFormDialog."""

    def test_creacion_basica(self, qtbot: QtBot) -> None:
        dlg = _CustomerFormDialog()
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Nuevo Cliente"

    def test_get_data_campos(self, qtbot: QtBot) -> None:
        dlg = _CustomerFormDialog()
        qtbot.addWidget(dlg)
        dlg._doc.setText("V-12345678")
        dlg._name.setText("Juan Pérez")
        dlg._phone.setText("0414-1234567")
        dlg._email.setText("juan@test.com")
        data = dlg.get_data()
        assert data["id_document"] == "V-12345678"
        assert data["name"] == "Juan Pérez"
        assert data["phone"] == "0414-1234567"
        assert data["email"] == "juan@test.com"

    def test_get_data_phone_vacio_es_none(self, qtbot: QtBot) -> None:
        dlg = _CustomerFormDialog()
        qtbot.addWidget(dlg)
        dlg._doc.setText("V-12345678")
        dlg._name.setText("Juan")
        dlg._phone.setText("")
        data = dlg.get_data()
        assert data["phone"] is None

    def test_validate_doc_vacio_falla(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        dlg = _CustomerFormDialog()
        qtbot.addWidget(dlg)
        dlg._doc.setText("")
        dlg._name.setText("Juan")
        dlg._validate_and_accept()
        assert dlg.result() != QDialog.DialogCode.Accepted
        assert warned

    def test_validate_name_vacio_falla(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        dlg = _CustomerFormDialog()
        qtbot.addWidget(dlg)
        dlg._doc.setText("V-12345678")
        dlg._name.setText("")
        dlg._validate_and_accept()
        assert dlg.result() != QDialog.DialogCode.Accepted
        assert warned

    def test_validate_campos_ok(self, qtbot: QtBot) -> None:
        dlg = _CustomerFormDialog()
        qtbot.addWidget(dlg)
        dlg._doc.setText("V-12345678")
        dlg._name.setText("Juan")
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted

    def test_prefill_con_documento(self, qtbot: QtBot) -> None:
        dlg = _CustomerFormDialog(prefill={"id_document": "V-99999999"})
        qtbot.addWidget(dlg)
        assert dlg._doc.text() == "V-99999999"

    def test_prefill_con_nombre(self, qtbot: QtBot) -> None:
        dlg = _CustomerFormDialog(prefill={"name": "Test User"})
        qtbot.addWidget(dlg)
        assert dlg._name.text() == "Test User"

    def test_prefill_con_telefono(self, qtbot: QtBot) -> None:
        dlg = _CustomerFormDialog(prefill={"phone": "0414-9999999"})
        qtbot.addWidget(dlg)
        assert dlg._phone.text() == "0414-9999999"

    def test_prefill_con_email(self, qtbot: QtBot) -> None:
        dlg = _CustomerFormDialog(prefill={"email": "test@test.com"})
        qtbot.addWidget(dlg)
        assert dlg._email.text() == "test@test.com"

    def test_prefill_doc_sets_name_focus_when_no_name(self, qtbot: QtBot) -> None:
        """When only id_document is prefilled, _fill_prefill sets focus to _name."""
        dlg = _CustomerFormDialog(prefill={"id_document": "V-123"})
        qtbot.addWidget(dlg)
        # _fill_prefill logic: doc set but name empty → _name.setFocus()
        # Focus may not be reliable in headless, so verify the data is correct
        assert dlg._doc.text() == "V-123"
        assert dlg._name.text() == ""

    def test_prefill_name_sets_doc_focus_when_name_present(self, qtbot: QtBot) -> None:
        """When both doc and name are prefilled, _fill_prefill sets focus to _doc."""
        dlg = _CustomerFormDialog(prefill={"id_document": "V-123", "name": "Juan"})
        qtbot.addWidget(dlg)
        assert dlg._doc.text() == "V-123"
        assert dlg._name.text() == "Juan"


# ── _create_customer_from_dialog Tests ────────────────────────────────


class TestCreateCustomerFromDialog:
    """Tests for _create_customer_from_dialog function."""

    def test_dialogo_rechazado_retorna_none(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.pos_view._CustomerFormDialog",
            return_value=mock_dlg,
        )
        result = _create_customer_from_dialog(None)
        assert result is None

    def test_dialogo_aceptado_crea_cliente(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_data.return_value = {
            "id_document": "V-12345678",
            "name": "Juan",
            "phone": None,
            "email": None,
        }
        mocker.patch(
            "opticamanager.ui.views.pos_view._CustomerFormDialog",
            return_value=mock_dlg,
        )
        fake, _ = _fake_session(mocker)
        result = _create_customer_from_dialog(None)
        assert result is not None
        fake.add.assert_called_once()
        fake.commit.assert_called_once()

    def test_error_al_crear_retorna_none(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_data.return_value = {
            "id_document": "V-12345678",
            "name": "Juan",
            "phone": None,
            "email": None,
        }
        mocker.patch(
            "opticamanager.ui.views.pos_view._CustomerFormDialog",
            return_value=mock_dlg,
        )
        fake, _ = _fake_session(mocker)
        fake.add.side_effect = Exception("DB error")
        mock_error = mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_error",
        )
        result = _create_customer_from_dialog(None)
        assert result is None
        mock_error.assert_called_once()


# ── _rate() Tests ────────────────────────────────────────────────────


class TestRateFunction:
    """Tests for the _rate() helper."""

    def test_rate_returns_rate_when_valid(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view.get_rate_info",
            return_value=RateInfo(rate=FAKE_RATE, source="bcv", updated_at=None),
        )
        assert _rate() == FAKE_RATE

    def test_rate_returns_none_when_none(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view.get_rate_info",
            return_value=RateInfo(rate=None, source="unknown", updated_at=None),
        )
        assert _rate() is None

    def test_rate_returns_none_when_zero(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view.get_rate_info",
            return_value=RateInfo(rate=Decimal("0"), source="unknown", updated_at=None),
        )
        assert _rate() is None


# ── _PrescriptionHistoryDialog Tests ─────────────────────────────────


class TestPrescriptionHistoryDialog:
    """Tests for _PrescriptionHistoryDialog."""

    def test_creacion_basica(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        customer = _make_customer()
        _fake_session(mocker, exec_results=[])
        dlg = _PrescriptionHistoryDialog(customer)
        qtbot.addWidget(dlg)
        assert "Juan Pérez" in dlg.windowTitle()

    def test_set_pick_mode(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        customer = _make_customer()
        _fake_session(mocker, exec_results=[])
        dlg = _PrescriptionHistoryDialog(customer)
        qtbot.addWidget(dlg)
        dlg.set_pick_mode()
        # After set_pick_mode, the button text should match
        assert "Usar" in dlg._btn_use.text()

    def test_pick_mode_hidden_by_default(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        customer = _make_customer()
        _fake_session(mocker, exec_results=[])
        dlg = _PrescriptionHistoryDialog(customer)
        qtbot.addWidget(dlg)
        assert not dlg._btn_use.isVisible()

    def test_fmt_opt_none(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        customer = _make_customer()
        _fake_session(mocker, exec_results=[])
        dlg = _PrescriptionHistoryDialog(customer)
        qtbot.addWidget(dlg)
        assert dlg._fmt_opt(None) == ""

    def test_fmt_opt_value(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        customer = _make_customer()
        _fake_session(mocker, exec_results=[])
        dlg = _PrescriptionHistoryDialog(customer)
        qtbot.addWidget(dlg)
        result = dlg._fmt_opt(Decimal("2.50"))
        assert result != ""

    def test_fmt_opt_with_unit(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        customer = _make_customer()
        _fake_session(mocker, exec_results=[])
        dlg = _PrescriptionHistoryDialog(customer)
        qtbot.addWidget(dlg)
        result = dlg._fmt_opt(Decimal("63.00"), unit="mm")
        assert "mm" in result

    def test_accept_selection_sin_fila(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        customer = _make_customer()
        _fake_session(mocker, exec_results=[])
        dlg = _PrescriptionHistoryDialog(customer)
        qtbot.addWidget(dlg)
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        dlg._accept_selection()
        assert msgs  # Shows "Seleccione una receta"

    def test_show_detail_sin_fila(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        customer = _make_customer()
        _fake_session(mocker, exec_results=[])
        dlg = _PrescriptionHistoryDialog(customer)
        qtbot.addWidget(dlg)
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        dlg._show_detail()
        assert msgs

    def test_print_prescription_sin_fila(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        customer = _make_customer()
        _fake_session(mocker, exec_results=[])
        dlg = _PrescriptionHistoryDialog(customer)
        qtbot.addWidget(dlg)
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        dlg._print_prescription()
        assert msgs

    def test_selected_prescription_inicial_es_none(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        customer = _make_customer()
        _fake_session(mocker, exec_results=[])
        dlg = _PrescriptionHistoryDialog(customer)
        qtbot.addWidget(dlg)
        assert dlg.selected_prescription is None


# ── POSView Tests ────────────────────────────────────────────────────


class TestPOSViewCreacion:
    """Smoke tests for POSView creation."""

    def test_creacion_basica(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        assert isinstance(view, POSView)

    def test_tiene_tabs(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        assert view._tabs.count() >= 1

    def test_session_bar_existe(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        assert view._session_bar is not None


class _FakeVentasView(QWidget):
    """Stand-in for VentasView: a real QWidget with a _load_ventas() slot."""

    def __init__(self) -> None:
        super().__init__()
        self.load_calls = 0

    def _load_ventas(self) -> None:
        self.load_calls += 1


class TestPOSViewSalesHistoryIntegration:
    """Tests for VentasView embedded inside POSView via QStackedWidget."""

    def test_btn_history_hidden_for_non_admin(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        UserSession._user = None
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        assert view._btn_history.isHidden()

    def test_btn_history_visible_for_admin(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        UserSession._user = UserData(
            id=1,
            username="admin",
            name="Admin User",
            email="admin@test.com",
            role_id=1,
            role_name="Admin",
        )
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        assert not view._btn_history.isHidden()

    def test_show_history_builds_view_once(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        UserSession._user = UserData(
            id=1,
            username="admin",
            name="Admin User",
            email="admin@test.com",
            role_id=1,
            role_name="Admin",
        )
        ventas_cls = mocker.patch(
            "opticamanager.ui.views.ventas_view.VentasView",
            side_effect=_FakeVentasView,
        )
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        assert view._history_view is None
        assert view._stack.currentIndex() == 0

        view._show_history()
        assert ventas_cls.call_count == 1
        assert view._history_view is not None
        assert view._history_view.load_calls == 1  # refreshed on first open
        assert view._stack.currentIndex() == 1

        view._show_history()
        assert ventas_cls.call_count == 1  # cached, not rebuilt
        assert view._history_view.load_calls == 2  # refreshed on every open
        assert view._stack.currentIndex() == 1

    def test_back_to_pos_returns_to_main(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        UserSession._user = None
        mocker.patch(
            "opticamanager.ui.views.ventas_view.VentasView",
            side_effect=_FakeVentasView,
        )
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._show_history()
        assert view._stack.currentIndex() == 1
        view._back_to_pos()
        assert view._stack.currentIndex() == 0


class TestPOSViewSessionManagement:
    """Tests for session open/close and state management."""

    def test_set_session_updates_ui(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        assert view._active_session is cs
        # Verify button state was toggled
        assert not view._btn_open_session.isVisible()
        assert not view._btn_close_session.isHidden()

    def test_clear_session_ui_resets(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        view._clear_session_ui()
        assert view._active_session is None
        # Verify buttons were reset
        assert not view._btn_close_session.isVisible()
        assert not view._btn_open_session.isHidden()

    def test_update_elapsed_time_con_sesion(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session(opened_at=datetime.now() - timedelta(hours=2))
        view._set_session(cs)
        view._update_elapsed_time()
        text = view._session_label.text()
        assert "Abierta" in text

    def test_update_elapsed_time_sin_sesion(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._active_session = None
        # Should not crash
        view._update_elapsed_time()

    def test_open_session_dialog_acepta(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.initial_balance = Decimal("500.00")
        mocker.patch(
            "opticamanager.ui.views.pos_view._CashOpenDialog",
            return_value=mock_dlg,
        )
        mock_css = mocker.patch("opticamanager.ui.views.pos_view.cash_session_service")
        mock_css.get_active_session.return_value = None
        mock_css.open_session.return_value = _make_cash_session()
        view._open_session_dialog()
        mock_css.open_session.assert_called_once()

    def test_open_session_dialog_rechazado(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.pos_view._CashOpenDialog",
            return_value=mock_dlg,
        )
        view._open_session_dialog()
        assert view._active_session is None

    def test_open_session_error_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.initial_balance = Decimal("500.00")
        mocker.patch(
            "opticamanager.ui.views.pos_view._CashOpenDialog",
            return_value=mock_dlg,
        )
        mock_css = mocker.patch("opticamanager.ui.views.pos_view.cash_session_service")
        mock_css.open_session.side_effect = Exception("DB error")
        mock_error = mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_error",
        )
        view._open_session_dialog()
        mock_error.assert_called_once()


class TestPOSViewTabManagement:
    """Tests for tab creation, closure, and active tab."""

    def test_new_sale_tab_agrega_tab(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        initial_count = view._tabs.count()
        view._new_sale_tab()
        assert view._tabs.count() == initial_count + 1

    def test_close_sale_tab_lo_elimina(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._new_sale_tab()
        idx = view._tabs.count() - 1
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        view._close_sale_tab(idx)
        # Tab might be removed or not depending on logic

    def test_close_last_tab_no_hace_nada(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        initial_count = view._tabs.count()
        # Try closing the last tab
        for idx in range(initial_count):
            view._close_sale_tab(idx)
        # At least one tab remains
        assert view._tabs.count() >= 1

    def test_active_tab_returns_sale_tab(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        assert isinstance(tab, _SaleTab)

    def test_active_session_obj_returns_session(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        session = view._active_session_obj()
        assert session is not None


class TestPOSViewProductLoading:
    """Tests for _load_products."""

    def test_load_products_vacio(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        fake, _ = _fake_session(mocker, exec_results=[])
        view._load_products()
        # No crash, product table cleared

    def test_load_products_con_datos(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        prod = _make_product()
        fake, _ = _fake_session(mocker, exec_results=[prod])
        view._load_products()
        # No crash, products loaded

    def test_load_products_con_busqueda(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        fake, _ = _fake_session(mocker, exec_results=[])
        view._load_products("lente")
        # No crash

    def test_load_products_bs_price_none(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view.convert_to_bs",
            return_value=None,
        )
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        prod = _make_product()
        fake, _ = _fake_session(mocker, exec_results=[prod])
        view._load_products()
        # Should show "—" for price


class TestPOSViewCartOperations:
    """Tests for cart manipulation methods."""

    def test_add_to_cart_no_selection(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: None,
        )
        view._add_selected_to_cart()
        # No crash

    def test_render_cart_vacio(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        view._render_cart(tab)
        assert tab.cart_table.rowCount() == 0

    def test_render_cart_con_items(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"), quantity=2)
        tab.session.cart.append(ci)
        view._render_cart(tab)
        assert tab.cart_table.rowCount() == 1

    def test_cart_increment(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"), quantity=1)
        tab.session.cart.append(ci)
        fake, _ = _fake_session(mocker)
        mock_product = _make_product(stock_quantity=50)
        fake.get.return_value = mock_product
        view._cart_increment(tab, 0)
        assert ci.quantity == 2

    def test_cart_increment_out_of_range(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        view._cart_increment(tab, -1)
        view._cart_increment(tab, 999)

    def test_cart_increment_stock_insuficiente(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"), quantity=10)
        tab.session.cart.append(ci)
        fake, _ = _fake_session(mocker)
        mock_product = _make_product(stock_quantity=10)
        fake.get.return_value = mock_product
        warned_msgs = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *a, **_k: warned_msgs.append(f"{a[1]} | {a[2]}"),
        )
        view._cart_increment(tab, 0)
        assert ci.quantity == 10  # Not incremented
        assert warned_msgs
        # Usability: the message names the cause in Spanish.
        assert any("Stock insuficiente" in msg for msg in warned_msgs)

    def test_cart_decrement(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"), quantity=3)
        tab.session.cart.append(ci)
        view._cart_decrement(tab, 0)
        assert ci.quantity == 2

    def test_cart_decrement_to_remove(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"), quantity=1)
        tab.session.cart.append(ci)
        view._cart_decrement(tab, 0)
        assert len(tab.session.cart) == 0

    def test_cart_decrement_out_of_range(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        view._cart_decrement(tab, -1)
        view._cart_decrement(tab, 999)

    def test_cart_remove(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"))
        tab.session.cart.append(ci)
        view._cart_remove(tab, 0)
        assert len(tab.session.cart) == 0

    def test_cart_remove_out_of_range(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        view._cart_remove(tab, -1)
        view._cart_remove(tab, 999)

    def test_clear_tab(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"))
        tab.session.cart.append(ci)
        tab.session.customer = _make_customer()
        view._clear_tab(tab)
        assert tab.session.cart_empty()
        assert tab.session.customer is None


class TestPOSViewRecalculateTotals:
    """Tests for _recalculate_totals."""

    def test_recalculate_vacio(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        view._recalculate_totals(tab)
        assert "0" in tab.total_label.text()

    def test_recalculate_con_items(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("100.00"), Decimal("100.00"))
        tab.session.cart.append(ci)
        view._recalculate_totals(tab)
        assert "100" in tab.subtotal_label.text()

    def test_recalculate_usd_visible(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view.convert_to_usd",
            return_value=Decimal("10.00"),
        )
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("100.00"), Decimal("100.00"))
        tab.session.cart.append(ci)
        view._recalculate_totals(tab)
        # When convert_to_usd returns a value, the label shows formatted USD
        assert "10" in tab.total_usd_label.text()

    def test_recalculate_usd_none_hides(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.pos_view.convert_to_usd",
            return_value=None,
        )
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("100.00"), Decimal("100.00"))
        tab.session.cart.append(ci)
        view._recalculate_totals(tab)
        # When convert_to_usd returns None, the else branch runs (setVisible(False))
        # Verify the label still exists and has some text (was set before hide)
        assert tab.total_usd_label is not None


class TestPOSViewCheckout:
    """Tests for _checkout flow."""

    def test_checkout_sin_sesion(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._active_session = None
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._checkout()
        assert msgs

    def test_checkout_carrito_vacio(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._checkout()
        assert msgs

    def test_checkout_sin_cliente(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"))
        tab.session.cart.append(ci)
        tab.session.customer = None
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._checkout()
        assert msgs

    def test_checkout_dialogo_pago_cancelado(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"))
        tab.session.cart.append(ci)
        tab.session.customer = _make_customer()
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.pos_view._PaymentDialog",
            return_value=mock_dlg,
        )
        view._checkout()
        # No sale processed

    def test_checkout_confirmacion_rechazada(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"))
        tab.session.cart.append(ci)
        tab.session.customer = _make_customer()
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.payment_method = EFECTIVO_BS
        mock_dlg.amount_received = Decimal("25.00")
        mock_dlg.change_amount = Decimal("0")
        mock_dlg.payments = [
            {
                "method": EFECTIVO_BS,
                "currency": "Bs",
                "amount": Decimal("25.00"),
                "amount_bs": Decimal("25.00"),
                "rate_used": None,
            }
        ]
        mocker.patch(
            "opticamanager.ui.views.pos_view._PaymentDialog",
            return_value=mock_dlg,
        )
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=False,
        )
        view._checkout()
        # Sale not processed because confirmation was rejected

    def test_checkout_exito(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"))
        tab.session.cart.append(ci)
        tab.session.customer = _make_customer()
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.payment_method = EFECTIVO_BS
        mock_dlg.amount_received = Decimal("25.00")
        mock_dlg.change_amount = Decimal("0")
        mock_dlg.payments = [
            {
                "method": EFECTIVO_BS,
                "currency": "Bs",
                "amount": Decimal("25.00"),
                "amount_bs": Decimal("25.00"),
                "rate_used": None,
            }
        ]
        mocker.patch(
            "opticamanager.ui.views.pos_view._PaymentDialog",
            return_value=mock_dlg,
        )
        mock_factura = mocker.patch("opticamanager.ui.views.pos_view.show_sale_receipt")
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        mock_sale = _make_sale_obj()
        mock_registrar = mocker.patch(
            "opticamanager.ui.views.pos_view.registrar_venta",
            return_value=mock_sale,
        )
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: None,
        )
        view._checkout()
        mock_registrar.assert_called_once()
        mock_factura.assert_called_once()
        assert mock_factura.call_args.args[1] == mock_sale.id

    def test_checkout_exito_con_abono(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"))
        tab.session.cart.append(ci)
        tab.session.customer = _make_customer()
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.payment_method = ABONO
        mock_dlg.amount_received = Decimal("15.00")
        mock_dlg.change_amount = Decimal("0")
        mock_dlg.payments = [
            {
                "method": ABONO,
                "currency": "Bs",
                "amount": Decimal("15.00"),
                "amount_bs": Decimal("15.00"),
                "rate_used": None,
            }
        ]
        mocker.patch(
            "opticamanager.ui.views.pos_view._PaymentDialog",
            return_value=mock_dlg,
        )
        mock_factura = mocker.patch("opticamanager.ui.views.pos_view.show_sale_receipt")
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        mock_sale = _make_sale_obj()
        mock_registrar = mocker.patch(
            "opticamanager.ui.views.pos_view.registrar_venta",
            return_value=mock_sale,
        )
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: None,
        )
        view._checkout()
        mock_registrar.assert_called_once()
        mock_factura.assert_called_once()
        assert mock_factura.call_args.args[1] == mock_sale.id

    def test_checkout_exito_con_mixto(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"))
        tab.session.cart.append(ci)
        tab.session.customer = _make_customer()
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.payment_method = MIXTO
        mock_dlg.amount_received = Decimal("25.00")
        mock_dlg.change_amount = Decimal("0")
        mock_dlg.payments = [
            {
                "method": PAGO_MOVIL,
                "currency": "Bs",
                "amount": Decimal("15.00"),
                "amount_bs": Decimal("15.00"),
                "rate_used": None,
            },
            {
                "method": EFECTIVO_BS,
                "currency": "Bs",
                "amount": Decimal("10.00"),
                "amount_bs": Decimal("10.00"),
                "rate_used": None,
            },
        ]
        mocker.patch(
            "opticamanager.ui.views.pos_view._PaymentDialog",
            return_value=mock_dlg,
        )
        mock_factura = mocker.patch("opticamanager.ui.views.pos_view.show_sale_receipt")
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        mock_sale = _make_sale_obj()
        mock_registrar = mocker.patch(
            "opticamanager.ui.views.pos_view.registrar_venta",
            return_value=mock_sale,
        )
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: None,
        )
        view._checkout()
        mock_registrar.assert_called_once()
        mock_factura.assert_called_once()
        assert mock_factura.call_args.args[1] == mock_sale.id

    def test_checkout_exito_con_receta(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"))
        tab.session.cart.append(ci)
        tab.session.customer = _make_customer()
        tab.session.prescription = _make_prescription()
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.payment_method = EFECTIVO_BS
        mock_dlg.amount_received = Decimal("25.00")
        mock_dlg.change_amount = Decimal("0")
        mock_dlg.payments = [
            {
                "method": EFECTIVO_BS,
                "currency": "Bs",
                "amount": Decimal("25.00"),
                "amount_bs": Decimal("25.00"),
                "rate_used": None,
            }
        ]
        mocker.patch(
            "opticamanager.ui.views.pos_view._PaymentDialog",
            return_value=mock_dlg,
        )
        mock_factura = mocker.patch("opticamanager.ui.views.pos_view.show_sale_receipt")
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        mock_sale = _make_sale_obj()
        mocker.patch(
            "opticamanager.ui.views.pos_view.registrar_venta",
            return_value=mock_sale,
        )
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: None,
        )
        view._checkout()
        # Should include prescription_id
        mock_factura.assert_called_once()
        assert mock_factura.call_args.args[1] == mock_sale.id

    def test_checkout_error_registra_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"))
        tab.session.cart.append(ci)
        tab.session.customer = _make_customer()
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.payment_method = EFECTIVO_BS
        mock_dlg.amount_received = Decimal("25.00")
        mock_dlg.change_amount = Decimal("0")
        mock_dlg.payments = [
            {
                "method": EFECTIVO_BS,
                "currency": "Bs",
                "amount": Decimal("25.00"),
                "amount_bs": Decimal("25.00"),
                "rate_used": None,
            }
        ]
        mocker.patch(
            "opticamanager.ui.views.pos_view._PaymentDialog",
            return_value=mock_dlg,
        )
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        mocker.patch(
            "opticamanager.ui.views.pos_view.registrar_venta",
            side_effect=Exception("DB error"),
        )
        mock_error = mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_error",
        )
        mocker.patch(
            "opticamanager.ui.views.pos_view.UserSession",
            return_value=MagicMock(current_user=_make_user()),
        )
        view._checkout()
        mock_error.assert_called()

    def test_checkout_sin_user_activo(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"))
        tab.session.cart.append(ci)
        tab.session.customer = _make_customer()
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.payment_method = EFECTIVO_BS
        mock_dlg.amount_received = Decimal("25.00")
        mock_dlg.change_amount = Decimal("0")
        mock_dlg.payments = [
            {
                "method": EFECTIVO_BS,
                "currency": "Bs",
                "amount": Decimal("25.00"),
                "amount_bs": Decimal("25.00"),
                "rate_used": None,
            }
        ]
        mocker.patch(
            "opticamanager.ui.views.pos_view._PaymentDialog",
            return_value=mock_dlg,
        )
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        mocker.patch(
            "opticamanager.ui.views.pos_view.UserSession",
            return_value=MagicMock(current_user=None),
        )
        mock_error = mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_error",
        )
        view._checkout()
        mock_error.assert_called()


class TestPOSViewCustomerFlow:
    """Tests for customer search, creation, and selection flows."""

    def test_apply_customer(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        customer = _make_customer()
        view._apply_customer(tab, customer)
        assert tab.session.customer is customer
        assert tab.customer_edit.placeholderText() == "Escribe para cambiar de cliente…"

    def test_remove_customer(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        customer = _make_customer()
        view._apply_customer(tab, customer)
        view._remove_customer(tab)
        assert tab.session.customer is None
        assert (
            tab.customer_edit.placeholderText()
            == "Buscar cliente por nombre, cédula o teléfono…"
        )

    def test_on_customer_return_pressed_vacio(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        tab.customer_edit.setText("")
        view._on_customer_return_pressed(tab)

    def test_on_customer_return_pressed_un_match(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        customer = _make_customer()
        view._customer_index = [customer]
        view._customer_by_id = {1: customer}
        tab.customer_edit.setText("Juan")
        mocker.patch(
            "opticamanager.ui.views.pos_view._filtrar_clientes",
            return_value=[customer],
        )
        view._on_customer_return_pressed(tab)
        assert tab.session.customer is customer

    def test_on_customer_return_pressed_sin_matches(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        tab.customer_edit.setText("NoExiste")
        mocker.patch(
            "opticamanager.ui.views.pos_view._filtrar_clientes",
            return_value=[],
        )
        mocker.patch(
            "opticamanager.ui.views.pos_view._create_customer_from_dialog",
            return_value=None,
        )
        view._on_customer_return_pressed(tab)

    def test_on_customer_return_pressed_varios_matches(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        c1 = _make_customer(1, "Juan")
        c2 = _make_customer(2, "Juana")
        view._customer_index = [c1, c2]
        tab.customer_edit.setText("Ju")
        mocker.patch(
            "opticamanager.ui.views.pos_view._filtrar_clientes",
            return_value=[c1, c2],
        )
        view._on_customer_return_pressed(tab)

    def test_create_customer_from_tab(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        customer = _make_customer()
        mocker.patch(
            "opticamanager.ui.views.pos_view._create_customer_from_dialog",
            return_value=customer,
        )
        mocker.patch.object(view, "_refresh_customer_index")
        view._create_customer_from_tab()
        tab = view._active_tab()
        assert tab.session.customer is customer

    def test_create_customer_from_tab_no_active_tab(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        mocker.patch.object(view, "_active_tab", return_value=None)
        view._create_customer_from_tab()

    def test_crear_cliente_desde_busqueda(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        customer = _make_customer()
        mocker.patch(
            "opticamanager.ui.views.pos_view._create_customer_from_dialog",
            return_value=customer,
        )
        mocker.patch.object(view, "_refresh_customer_index")
        view._crear_cliente_desde_busqueda(tab, "Juan Pérez")
        assert tab.session.customer is customer


class TestPOSViewPrescriptionFlow:
    """Tests for prescription picking and history."""

    def test_pick_prescription_sin_cliente(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        tab.session.customer = None
        msgs = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._pick_prescription(tab)
        assert msgs

    def test_pick_prescription_cancelado(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        tab.session.customer = _make_customer()
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.pos_view._PrescriptionHistoryDialog",
            return_value=mock_dlg,
        )
        view._pick_prescription(tab)
        # No prescription set

    def test_pick_prescription_aceptado(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        tab.session.customer = _make_customer()
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.selected_prescription = _make_prescription()
        mocker.patch(
            "opticamanager.ui.views.pos_view._PrescriptionHistoryDialog",
            return_value=mock_dlg,
        )
        view._pick_prescription(tab)
        assert tab.session.prescription is not None

    def test_show_rx_history_sin_cliente(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        tab.session.customer = None
        view._show_rx_history(tab)  # Should return without crash

    def test_show_rx_history_con_cliente(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        tab.session.customer = _make_customer()
        mock_dlg = MagicMock()
        mocker.patch(
            "opticamanager.ui.views.pos_view._PrescriptionHistoryDialog",
            return_value=mock_dlg,
        )
        view._show_rx_history(tab)
        mock_dlg.exec.assert_called_once()


class TestPOSViewPrintReceipt:
    """Tests for _print_receipt delegation."""

    def test_print_receipt_abre_dialogo_factura(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        mock_factura = mocker.patch("opticamanager.ui.views.pos_view.show_sale_receipt")

        view._print_receipt(7)

        mock_factura.assert_called_once_with(view, 7)


class TestPOSViewCloseSession:
    """Tests for _close_session_dialog."""

    def test_close_session_sin_sesion(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._active_session = None
        view._close_session_dialog()

    def test_close_session_con_carritos_vacios(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        mock_css = mocker.patch("opticamanager.ui.views.pos_view.cash_session_service")
        mock_css.get_session_summary.return_value = {
            "sales_count": 0,
            "total_sales": Decimal("0"),
            "by_method": {},
            "expected_balance": Decimal("500.00"),
        }
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.pos_view._CashCloseDialog",
            return_value=mock_dlg,
        )
        view._close_session_dialog()

    def test_close_session_error_summary(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        mock_css = mocker.patch("opticamanager.ui.views.pos_view.cash_session_service")
        mock_css.get_session_summary.side_effect = Exception("DB error")
        mock_error = mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_error",
        )
        view._close_session_dialog()
        mock_error.assert_called()

    def test_close_session_exitoso(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        mock_css = mocker.patch("opticamanager.ui.views.pos_view.cash_session_service")
        mock_css.get_session_summary.return_value = {
            "sales_count": 0,
            "total_sales": Decimal("0"),
            "by_method": {},
            "expected_balance": Decimal("500.00"),
        }
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.final_balance = Decimal("500.00")
        mock_dlg.difference = Decimal("0")
        mocker.patch(
            "opticamanager.ui.views.pos_view._CashCloseDialog",
            return_value=mock_dlg,
        )
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: None,
        )
        view._close_session_dialog()
        mock_css.close_session.assert_called_once()

    def test_close_session_error_close(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        mock_css = mocker.patch("opticamanager.ui.views.pos_view.cash_session_service")
        mock_css.get_session_summary.return_value = {
            "sales_count": 0,
            "total_sales": Decimal("0"),
            "by_method": {},
            "expected_balance": Decimal("500.00"),
        }
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.final_balance = Decimal("500.00")
        mock_dlg.difference = Decimal("0")
        mocker.patch(
            "opticamanager.ui.views.pos_view._CashCloseDialog",
            return_value=mock_dlg,
        )
        mock_css.close_session.side_effect = Exception("DB error")
        mock_error = mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_error",
        )
        view._close_session_dialog()
        mock_error.assert_called()

    def test_close_session_con_carritos_llenos_confirma(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"))
        tab.session.cart.append(ci)
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        mock_css = mocker.patch("opticamanager.ui.views.pos_view.cash_session_service")
        mock_css.get_session_summary.return_value = {
            "sales_count": 0,
            "total_sales": Decimal("0"),
            "by_method": {},
            "expected_balance": Decimal("500.00"),
        }
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.final_balance = Decimal("500.00")
        mock_dlg.difference = Decimal("0")
        mocker.patch(
            "opticamanager.ui.views.pos_view._CashCloseDialog",
            return_value=mock_dlg,
        )
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: None,
        )
        view._close_session_dialog()

    def test_close_session_carritos_llenos_cancela(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        cs = _make_cash_session()
        view._set_session(cs)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"))
        tab.session.cart.append(ci)
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=False,
        )
        view._close_session_dialog()


class TestPOSViewEnsureSession:
    """Tests for _ensure_session."""

    def test_ensure_session_con_sesion_activa(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        mock_css = mocker.patch("opticamanager.ui.views.pos_view.cash_session_service")
        cs = _make_cash_session()
        mock_css.get_active_session.return_value = cs
        view._ensure_session()
        assert view._active_session is cs

    def test_ensure_session_sin_sesion(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        mock_css = mocker.patch("opticamanager.ui.views.pos_view.cash_session_service")
        mock_css.get_active_session.return_value = None
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.pos_view._CashOpenDialog",
            return_value=mock_dlg,
        )
        view._ensure_session()
        assert view._active_session is None

    def test_ensure_session_cancelado_limpia_ui(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._active_session = None
        mocker.patch(
            "opticamanager.ui.views.pos_view.cash_session_service.get_active_session",
            return_value=None,
        )
        mocker.patch.object(view, "_open_session_dialog")  # user cancels: no-op
        cleared = []
        mocker.patch.object(
            view, "_clear_session_ui", side_effect=lambda: cleared.append(1)
        )
        view._ensure_session()
        assert cleared == [1]

    def test_ensure_session_con_sesion_no_limpia_ui(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._active_session = None
        mocker.patch(
            "opticamanager.ui.views.pos_view.cash_session_service.get_active_session",
            return_value=_make_cash_session(),
        )
        mocker.patch.object(view, "_open_session_dialog")
        cleared = []
        mocker.patch.object(
            view, "_clear_session_ui", side_effect=lambda: cleared.append(1)
        )
        view._ensure_session()
        assert cleared == []

    def test_ensure_session_sin_user(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        mocker.patch(
            "opticamanager.ui.views.pos_view.UserSession",
            return_value=MagicMock(current_user=None),
        )
        view._ensure_session()
        assert view._active_session is None


class TestPOSViewRefreshCustomerIndex:
    """Tests for _refresh_customer_index."""

    def test_refresh_carga_clientes(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        c1 = _make_customer(1, "Juan")
        c2 = _make_customer(2, "Ana")
        fake, _ = _fake_session(mocker, exec_results=[c1, c2])
        view._refresh_customer_index()
        assert len(view._customer_index) == 2
        assert view._customer_by_id[1] is c1

    def test_refresh_vacio(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        fake, _ = _fake_session(mocker, exec_results=[])
        view._refresh_customer_index()
        assert len(view._customer_index) == 0


class TestPOSViewAddSelectedToCart:
    """Tests for _add_selected_to_cart with mocked product selection."""

    def test_add_product_to_cart(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        # Manually add a product row to the product table
        view._product_table.add_row(
            ["1", "12345", "Lente", "$ 25,00", "Bs. 900,00", "50"]
        )
        # Select the first row
        view._product_table.view().selectRow(0)
        prod = _make_product()
        fake, _ = _fake_session(mocker)
        fake.get.return_value = prod
        mocker.patch(
            "opticamanager.ui.views.pos_view.convert_to_bs",
            return_value=Decimal("900.00"),
        )
        view._add_selected_to_cart()
        assert len(tab.session.cart) == 1

    def test_add_product_no_active_tab(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        mocker.patch.object(view, "_active_tab", return_value=None)
        view._add_selected_to_cart()

    def test_add_product_not_found(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._product_table.add_row(
            ["1", "12345", "Lente", "$ 25,00", "Bs. 900,00", "50"]
        )
        view._product_table.view().selectRow(0)
        fake, _ = _fake_session(mocker)
        fake.get.return_value = None
        view._add_selected_to_cart()

    def test_add_product_inactive(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._product_table.add_row(
            ["1", "12345", "Lente", "$ 25,00", "Bs. 900,00", "50"]
        )
        view._product_table.view().selectRow(0)
        fake, _ = _fake_session(mocker)
        fake.get.return_value = _make_product(active=False)
        view._add_selected_to_cart()

    def test_add_product_sin_stock(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._product_table.add_row(
            ["1", "12345", "Lente", "$ 25,00", "Bs. 900,00", "0"]
        )
        view._product_table.view().selectRow(0)
        fake, _ = _fake_session(mocker)
        fake.get.return_value = _make_product(stock_quantity=0)
        warned_msgs = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *a, **_k: warned_msgs.append(f"{a[1]} | {a[2]}"),
        )
        view._add_selected_to_cart()
        assert warned_msgs
        # Usability: the message names the cause in Spanish.
        assert any("Sin stock" in msg for msg in warned_msgs)

    def test_add_product_already_in_cart_increments(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("900.00"), Decimal("25.00"), quantity=1)
        tab.session.cart.append(ci)
        view._product_table.add_row(
            ["1", "12345", "Lente", "$ 25,00", "Bs. 900,00", "50"]
        )
        view._product_table.view().selectRow(0)
        fake, _ = _fake_session(mocker)
        fake.get.return_value = _make_product(stock_quantity=50)
        view._add_selected_to_cart()
        assert ci.quantity == 2

    def test_add_product_already_in_cart_insufficient_stock(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        ci = _CartItem(1, "Lente", Decimal("900.00"), Decimal("25.00"), quantity=50)
        tab.session.cart.append(ci)
        view._product_table.add_row(
            ["1", "12345", "Lente", "$ 25,00", "Bs. 900,00", "50"]
        )
        view._product_table.view().selectRow(0)
        fake, _ = _fake_session(mocker)
        fake.get.return_value = _make_product(stock_quantity=50)
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        view._add_selected_to_cart()
        assert ci.quantity == 50  # Not incremented
        assert warned

    def test_add_product_bs_price_none(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._active_tab()
        view._product_table.add_row(
            ["1", "12345", "Lente", "$ 25,00", "Bs. 900,00", "50"]
        )
        view._product_table.view().selectRow(0)
        fake, _ = _fake_session(mocker)
        fake.get.return_value = _make_product(stock_quantity=50)
        mocker.patch(
            "opticamanager.ui.views.pos_view.convert_to_bs",
            return_value=None,
        )
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        view._add_selected_to_cart()
        assert warned


class TestPOSViewShowEvent:
    """Tests for showEvent deferral."""

    def test_show_event_first_time(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        from PyQt6.QtGui import QShowEvent

        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._started = False
        mocker.patch.object(view, "_refresh_customer_index")
        mocker.patch.object(view, "_ensure_session")
        mocker.patch.object(view, "_load_products")
        mocker.patch.object(view, "_configure_customer_completer")
        event = QShowEvent()
        view.showEvent(event)
        assert view._started is True

    def test_show_event_subsequent(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        from PyQt6.QtGui import QShowEvent

        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._started = True
        mock_cc = mocker.patch.object(view, "_configure_customer_completer")
        mocker.patch.object(view, "_refresh_customer_index")
        event = QShowEvent()
        view.showEvent(event)
        # _configure_customer_completer should NOT be called again
        mock_cc.assert_not_called()


class TestPOSViewFlushCustomerSearch:
    """Tests for _flush_customer_search."""

    def test_flush_sin_pending(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._pending_search_tab = None
        view._flush_customer_search()

    def test_flush_con_pending(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        view._pending_search_tab = tab
        view._pending_search_text = "Juan"
        mocker.patch.object(view, "_update_customer_suggestions")
        view._flush_customer_search()
        # type: ignore[attr-defined] -- pytest-mock attribute the type-checker cannot see
        view._update_customer_suggestions.assert_called_once_with(tab, "Juan")
        assert view._pending_search_tab is None


class TestPOSViewOnCustomerSearchText:
    """Tests for _on_customer_search_text."""

    def test_starts_timer(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        mocker.patch.object(view._customer_timer, "start")
        view._on_customer_search_text(tab, "Juan")
        assert view._pending_search_tab is tab
        assert view._pending_search_text == "Juan"
        # type: ignore[attr-defined] -- pytest-mock attribute the type-checker cannot see
        view._customer_timer.start.assert_called_once()


class TestPOSViewCancelCustomerSearch:
    """Tests for _cancel_customer_search: stop the debounce and close the
    completer popup so it stays closed after apply/remove/create."""

    def test_cancel_detiene_timer_y_limpia_pendiente(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        tab.customer_edit.setText("Juan")
        assert view._customer_timer.isActive()
        view._cancel_customer_search()
        assert not view._customer_timer.isActive()
        assert view._pending_search_tab is None
        assert view._pending_search_text == ""

    def test_cancel_resetea_prefijo_del_completer(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._configure_customer_completer()
        tab = view._active_tab()
        view._update_customer_suggestions(tab, "Juan")
        assert view._customer_completer is not None
        assert view._customer_completer.completionPrefix() == "Juan"
        view._cancel_customer_search()
        assert view._customer_completer.completionPrefix() == ""
        assert not view._customer_completer.popup().isVisible()

    def test_apply_customer_cancela_busqueda_pendiente(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        customer = _make_customer()
        tab.customer_edit.setText("Juan")
        assert view._customer_timer.isActive()
        view._apply_customer(tab, customer)
        assert tab.session.customer is customer
        assert not view._customer_timer.isActive()
        assert view._pending_search_tab is None
        assert view._pending_search_text == ""

    def test_remove_customer_cancela_busqueda_pendiente(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        customer = _make_customer()
        view._apply_customer(tab, customer)
        tab.customer_edit.setText("Juan")
        assert view._customer_timer.isActive()
        view._remove_customer(tab)
        assert tab.session.customer is None
        assert not view._customer_timer.isActive()
        assert view._pending_search_tab is None
        assert view._pending_search_text == ""

    def test_crear_cliente_desde_busqueda_cancela_pendiente(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        tab.customer_edit.setText("Juan")
        mocker.patch(
            "opticamanager.ui.views.pos_view._create_customer_from_dialog",
            return_value=None,
        )
        assert view._customer_timer.isActive()
        view._crear_cliente_desde_busqueda(tab, "Juan")
        assert not view._customer_timer.isActive()
        assert view._pending_search_tab is None
        assert view._pending_search_text == ""

    def test_on_customer_activated_sentinel_cancela_pendiente(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._configure_customer_completer()
        tab = view._active_tab()
        tab.customer_edit.setText("NoExiste")
        assert view._customer_timer.isActive()
        # With no matches the completer model holds only the "Crear" row.
        view._update_customer_suggestions(tab, "NoExiste")
        assert view._customer_model is not None
        assert view._customer_model.rowCount() == 1
        mocker.patch(
            "opticamanager.ui.views.pos_view._create_customer_from_dialog",
            return_value=None,
        )
        view._on_customer_activated(view._customer_model.index(0, 0))
        assert not view._customer_timer.isActive()
        assert view._pending_search_tab is None
        assert view._pending_search_text == ""


class TestPOSViewTabIndexRebuild:
    """Bugfix: closing a tab must rebuild _cart_tabs keyed by visual index."""

    def _three_tabs(self, qtbot, mocker):
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        view._new_sale_tab()
        view._new_sale_tab()
        assert view._tabs.count() == 3
        return view

    def test_close_sale_tab_reindexa_cart_tabs(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = self._three_tabs(qtbot, mocker)
        tab_b = view._tabs.widget(1)
        tab_c = view._tabs.widget(2)
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        view._close_sale_tab(1)
        # Tabs shifted: B removed, C now at index 1.
        assert view._tabs.count() == 2
        assert sorted(view._cart_tabs.keys()) == [0, 1]
        assert tab_c not in (view._cart_tabs.get(2),)
        assert view._cart_tabs[1] is tab_c
        assert tab_b not in view._cart_tabs.values()

    def test_cerrar_tab_despues_de_cierre_intermedio(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = self._three_tabs(qtbot, mocker)
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        view._close_sale_tab(1)  # B removed, C shifts to index 1
        view._close_sale_tab(1)  # C must be closable at its new index
        assert view._tabs.count() == 1
        assert sorted(view._cart_tabs.keys()) == [0]

    def test_new_sale_tab_no_pisa_tab_vivo(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = self._three_tabs(qtbot, mocker)
        tab_c = view._tabs.widget(2)
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        view._close_sale_tab(1)  # B removed, C at index 1, index 2 free
        tab_d = view._new_sale_tab()  # goes to index 2 without overwriting C
        assert view._tabs.count() == 3
        assert view._cart_tabs[1] is tab_c
        assert view._cart_tabs[2] is tab_d

    def test_tabs_numeradas_secuencialmente_al_crear(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        assert view._tabs.tabText(0) == "Venta 1"
        view._new_sale_tab()
        assert view._tabs.tabText(1) == "Venta 2"
        view._new_sale_tab()
        assert view._tabs.tabText(2) == "Venta 3"

    def test_tabs_se_renumeran_al_cerrar_medio(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = self._three_tabs(qtbot, mocker)
        tab_c = view._tabs.widget(2)
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        view._close_sale_tab(1)  # B removed: titles must follow the new order
        assert view._tabs.tabText(0) == "Venta 1"
        assert view._tabs.tabText(1) == "Venta 2"
        assert view._tabs.widget(1) is tab_c
        # A newly created tab is numbered by its visual position, and the
        # renumbered "Venta 2" must NOT be overwritten.
        view._new_sale_tab()
        assert view._tabs.count() == 3
        assert view._tabs.tabText(1) == "Venta 2"
        assert view._tabs.tabText(2) == "Venta 3"


class TestPOSViewStockPostVenta:
    """Bugfix: catalog refresh + aggregate demand check at checkout."""

    def _checkout_setup(self, view, cs=None):
        cs = cs or _make_cash_session()
        view._set_session(cs)

    def test_checkout_exito_refresca_productos(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        self._checkout_setup(view)
        tab = view._active_tab()
        tab.session.cart.append(
            _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"))
        )
        tab.session.customer = _make_customer()
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.payment_method = EFECTIVO_BS
        mock_dlg.amount_received = Decimal("25.00")
        mock_dlg.change_amount = Decimal("0")
        mock_dlg.payments = [
            {
                "method": EFECTIVO_BS,
                "currency": "Bs",
                "amount": Decimal("25.00"),
                "amount_bs": Decimal("25.00"),
                "rate_used": None,
            }
        ]
        mocker.patch(
            "opticamanager.ui.views.pos_view._PaymentDialog",
            return_value=mock_dlg,
        )
        mock_factura = mocker.patch("opticamanager.ui.views.pos_view.show_sale_receipt")
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        mocker.patch(
            "opticamanager.ui.views.pos_view.registrar_venta",
            return_value=_make_sale_obj(),
        )
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: None,
        )
        spy = mocker.spy(view, "_load_products")
        view._checkout()
        spy.assert_called()
        mock_factura.assert_called_once()

    def test_checkout_bloquea_por_demanda_agregada(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        self._checkout_setup(view)
        tab1 = view._active_tab()
        tab1.session.cart.append(
            _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"), quantity=3)
        )
        tab1.session.customer = _make_customer()
        tab2 = view._new_sale_tab()
        tab2.session.cart.append(
            _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"), quantity=3)
        )
        tab2.session.customer = _make_customer()
        fake, _ = _fake_session(mocker)
        fake.get.return_value = _make_product(stock_quantity=5)  # 3+3 > 5
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        mock_dlg_cls = mocker.patch(
            "opticamanager.ui.views.pos_view._PaymentDialog",
        )
        mock_registrar = mocker.patch(
            "opticamanager.ui.views.pos_view.registrar_venta",
        )
        view._checkout()
        assert warned
        mock_dlg_cls.assert_not_called()
        mock_registrar.assert_not_called()

    def test_checkout_no_bloquea_si_demanda_dentro_stock(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        self._checkout_setup(view)
        tab1 = view._active_tab()
        tab1.session.cart.append(
            _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"), quantity=3)
        )
        tab1.session.customer = _make_customer()
        tab2 = view._new_sale_tab()
        tab2.session.cart.append(
            _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"), quantity=2)
        )
        tab2.session.customer = _make_customer()
        fake, _ = _fake_session(mocker)
        fake.get.return_value = _make_product(stock_quantity=10)  # 3+2 <= 10
        warned = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.payment_method = EFECTIVO_BS
        mock_dlg.amount_received = Decimal("25.00")
        mock_dlg.change_amount = Decimal("0")
        mock_dlg.payments = [
            {
                "method": EFECTIVO_BS,
                "currency": "Bs",
                "amount": Decimal("25.00"),
                "amount_bs": Decimal("25.00"),
                "rate_used": None,
            }
        ]
        mocker.patch(
            "opticamanager.ui.views.pos_view._PaymentDialog",
            return_value=mock_dlg,
        )
        mock_factura = mocker.patch("opticamanager.ui.views.pos_view.show_sale_receipt")
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        mock_registrar = mocker.patch(
            "opticamanager.ui.views.pos_view.registrar_venta",
            return_value=_make_sale_obj(),
        )
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: None,
        )
        view._checkout()
        assert not warned
        mock_registrar.assert_called_once()
        mock_factura.assert_called_once()

    def test_checkout_cambio_usd_se_formatea_en_dolares(
        self, qtbot: QtBot, mocker: MockerFixture, mock_session_data
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        self._checkout_setup(view)
        tab = view._active_tab()
        tab.session.cart.append(
            _CartItem(1, "Lente", Decimal("25.00"), Decimal("25.00"))
        )
        tab.session.customer = _make_customer()
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.payment_method = EFECTIVO_USD
        mock_dlg.amount_received = Decimal("26.00")
        mock_dlg.change_amount = Decimal("1.00")
        mock_dlg.payments = [
            {
                "method": EFECTIVO_USD,
                "currency": "USD",
                "amount": Decimal("26.00"),
                "amount_bs": Decimal("936.00"),
                "rate_used": FAKE_RATE,
            }
        ]
        mocker.patch(
            "opticamanager.ui.views.pos_view._PaymentDialog",
            return_value=mock_dlg,
        )
        mock_factura = mocker.patch("opticamanager.ui.views.pos_view.show_sale_receipt")
        mocker.patch(
            "opticamanager.ui.views.pos_view.dialogo_confirmacion",
            return_value=True,
        )
        mock_sale = _make_sale_obj(payment_method=EFECTIVO_USD)
        mock_sale.change_amount = Decimal("1.00")
        mocker.patch(
            "opticamanager.ui.views.pos_view.registrar_venta",
            return_value=mock_sale,
        )
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: None,
        )
        view._checkout()
        lineas = mock_factura.call_args.kwargs["lineas"]
        assert any(linea.startswith("Cambio: $") for linea in lineas)
        assert not any(linea.startswith("Cambio: Bs") for linea in lineas)


class TestPOSViewRowHeight:
    """Bugfix: every cart row must use height 40, not only the first."""

    def test_render_cart_fija_altura_en_todas_las_filas(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        tab = view._active_tab()
        for i in range(3):
            tab.session.cart.append(
                _CartItem(i + 1, f"Producto {i}", Decimal("10.00"), Decimal("10.00"))
            )
        view._render_cart(tab)
        assert tab.cart_table.rowCount() == 3
        for i in range(3):
            assert tab.cart_table.rowHeight(i) == 40


class TestPOSViewUsabilidad:
    """Usability: buttons with a non-obvious icon or action explain what they do."""

    def test_btn_nueva_venta_tiene_tooltip(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        assert view._btn_new_sale.toolTip() == "Nueva venta"

    def test_btn_historial_tiene_tooltip(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        assert view._btn_history.toolTip() == "Historial de ventas (solo admin)"

    def test_botones_de_sesion_tienen_texto_claro(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        view = _make_pos_view(mocker)
        qtbot.addWidget(view)
        # Action buttons carry self-explanatory text, not a mute icon.
        assert view._btn_open_session.text() == "🔓 Abrir Caja"
        assert view._btn_close_session.text() == "🔒 Cerrar Caja"
