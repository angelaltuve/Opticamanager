"""ALFA tests: headless E2E flows against the real isolated database.

They drive the application the way a user would: admin registration, real
login, real cash session opening, a full real sale (product/customer/invoice/
stock), and navigation through every sidebar section.

Only external services get patched (the BCV rate, which avoids a real HTTPS
call to www.bcv.org.ve that hangs without network) along with the modal dialogs
that would block a headless run (cash session/payment/confirmations). The
database, sessions, products, customers and the sale itself are REAL against the
isolated test database.

Qt behaviour note: on the first offscreen ``show()`` of the MainWindow, the
collapsed lazy pages receive a ``showEvent`` too (not only the active one), so
POSView and its ExchangeRateWidget get built while the window appears. That is
why the rate patch applies at module level and to the widget, and why every
flow patches the modal dialogs.

Requires: QT_QPA_PLATFORM=offscreen env -u QT_QPA_PLATFORMTHEME uv run pytest
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Iterator, cast
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication
from sqlmodel import select

from opticamanager.core.session import UserSession
from opticamanager.db import SessionManager
from opticamanager.models import (
    CashSession,
    Customer,
    InventoryLog,
    Product,
    Sale,
    SaleDetail,
    SalePayment,
    SaleStatus,
    User,
)
from opticamanager.services import cash_session_service
from opticamanager.services.exchange_rate import RateInfo
from opticamanager.ui.login_window import LoginWindow
from opticamanager.ui.main_window import MainWindow
from opticamanager.ui.views.pos_view import POSView

FAKE_RATE = Decimal("36.00")
ADMIN_USER = "alfa_admin"
ADMIN_PASS = "AlfaClave#2026"
ADMIN_EMAIL = "alfa.admin@test.com"


# ── Helpers ────────────────────────────────────────────────────────


def _fake_convert_usd(bolivares: Decimal, rate: Decimal | None = None) -> Decimal:
    return (bolivares / FAKE_RATE).quantize(Decimal("0.01"))


def _fake_convert_bs(dollars: Decimal, rate: Decimal | None = None) -> Decimal:
    return (dollars * FAKE_RATE).quantize(Decimal("0.01"))


def _fake_rate_info() -> RateInfo:
    return RateInfo(rate=FAKE_RATE, source="manual", updated_at=datetime.now())


# ── Fixtures ───────────────────────────────────────────────────────


def _ensure_sale_statuses() -> None:
    """Seed the status IDs used by the real POS checkout service."""
    statuses = {
        1: "Completada",
        2: "Pendiente",
        3: "Cancelada",
        4: "Rembolsada",
    }
    with SessionManager() as session:
        for status_id, name in statuses.items():
            status = session.get(SaleStatus, status_id)
            if status is None:
                session.add(SaleStatus(id=status_id, name=name))
            else:
                status.name = name
        session.commit()


def _delete_admin_if_exists() -> None:
    """Remove only this fixture user and the rows that reference it."""
    with SessionManager() as session:
        user = session.exec(select(User).where(User.username == ADMIN_USER)).first()
        if user is None or user.id is None:
            return

        user_id = user.id
        for sale in session.exec(select(Sale).where(Sale.user_id == user_id)).all():
            if sale.id is None:
                continue
            for detail in session.exec(
                select(SaleDetail).where(SaleDetail.sale_id == sale.id)
            ).all():
                session.delete(detail)
            for payment in session.exec(
                select(SalePayment).where(SalePayment.sale_id == sale.id)
            ).all():
                session.delete(payment)
            session.delete(sale)

        for inventory_log in session.exec(
            select(InventoryLog).where(InventoryLog.user_id == user_id)
        ).all():
            session.delete(inventory_log)

        for cash_session in session.exec(
            select(CashSession).where(CashSession.user_id == user_id)
        ).all():
            session.delete(cash_session)

        session.delete(user)
        session.commit()


def _reset_user_session() -> None:
    """Prevent this module's singleton instance from shadowing test fixtures."""
    session_obj = UserSession()
    session_obj.logout()
    session_obj.__dict__.pop("_user", None)
    UserSession._user = None
    UserSession._instance = None


@pytest.fixture(scope="module")
def admin_created() -> Iterator[None]:
    """Ensure a real admin exists in the isolated test DB (module scope)."""
    _delete_admin_if_exists()
    _ensure_sale_statuses()
    err = UserSession.register_admin(ADMIN_USER, "Admin Alfa", ADMIN_EMAIL, ADMIN_PASS)
    assert err is None, f"register_admin falló: {err}"
    yield
    # Leave the isolated DB without the admin to avoid interfering with other tests
    _delete_admin_if_exists()
    _reset_user_session()


@pytest.fixture()
def logged_admin(admin_created: None) -> Iterator[UserSession]:
    """Real login as the ALFA admin (fresh session each test)."""
    session_obj = UserSession()
    assert session_obj.login(ADMIN_USER, ADMIN_PASS) is True
    yield session_obj
    session_obj.logout()


@pytest.fixture()
def fake_rate(mocker):
    """Stub only the external BCV rate everywhere it is reachable."""
    from opticamanager.services import exchange_rate
    from opticamanager.ui.views import abonos_view, pos_view, reportes_view
    from opticamanager.ui.widgets import exchange_rate_widget

    ri = _fake_rate_info()
    # Service module: reportes_view (get_usd_rate around line 602), abonos_view
    # (get_rate_info around line 288) and any direct conversions.
    mocker.patch.object(exchange_rate, "get_usd_rate", return_value=FAKE_RATE)
    mocker.patch.object(exchange_rate, "get_rate_info", return_value=ri)
    mocker.patch.object(exchange_rate, "force_refresh", return_value=ri)
    mocker.patch.object(exchange_rate, "convert_to_bs", side_effect=_fake_convert_bs)
    mocker.patch.object(exchange_rate, "convert_to_usd", side_effect=_fake_convert_usd)
    # POS widget: its showEvent calls force_refresh/get_rate_info.
    mocker.patch.object(exchange_rate_widget, "force_refresh", return_value=ri)
    mocker.patch.object(exchange_rate_widget, "get_rate_info", return_value=ri)
    # POSView: direct imports from pos_view.
    mocker.patch.object(pos_view, "get_rate_info", return_value=ri)
    mocker.patch.object(pos_view, "get_usd_rate", return_value=FAKE_RATE)
    mocker.patch.object(pos_view, "convert_to_bs", side_effect=_fake_convert_bs)
    mocker.patch.object(pos_view, "convert_to_usd", side_effect=_fake_convert_usd)
    mocker.patch.object(abonos_view, "get_rate_info", return_value=ri)
    mocker.patch.object(reportes_view, "get_usd_rate", return_value=FAKE_RATE)


@pytest.fixture()
def modal_dialogs(mocker) -> None:
    """Replace modal dialogs that would block headless execution."""
    from opticamanager.ui.views import pos_view

    fake_open = MagicMock()
    fake_open.exec.return_value = 1  # QDialog.DialogCode.Accepted
    fake_open.initial_balance = Decimal("500.00")
    mocker.patch.object(pos_view, "_CashOpenDialog", return_value=fake_open)

    fake_pay = MagicMock()
    fake_pay.exec.return_value = 1
    fake_pay.payment_method = "Efectivo Bs"
    fake_pay.amount_received = Decimal("1044.00")
    fake_pay.change_amount = Decimal("0.00")
    fake_pay.payments = [
        {
            "method": "Efectivo Bs",
            "currency": "Bs",
            "amount": Decimal("1044.00"),
            "amount_bs": Decimal("1044.00"),
            "rate_used": None,
        }
    ]
    mocker.patch.object(pos_view, "_PaymentDialog", return_value=fake_pay)

    fake_close = MagicMock()
    fake_close.exec.return_value = 1
    fake_close.final_balance = Decimal("1544.00")
    fake_close.difference = Decimal("0.00")
    mocker.patch.object(pos_view, "_CashCloseDialog", return_value=fake_close)

    # Confirm the sale but do NOT print a receipt
    mocker.patch(
        "opticamanager.ui.views.pos_view.dialogo_confirmacion",
        side_effect=[True, False],
    )
    mocker.patch("opticamanager.ui.views.pos_view.dialogo_error")
    mocker.patch("PyQt6.QtWidgets.QMessageBox.information")
    mocker.patch("PyQt6.QtWidgets.QMessageBox.warning")


def _crear_producto_real(barcode: str, nombre: str) -> Product:
    with SessionManager() as session:
        prod = Product(
            name=nombre,
            barcode=barcode,
            cost_price_usd=Decimal("10.00"),
            sale_price_usd=Decimal("25.00"),
            stock_quantity=10,
            active=True,
        )
        session.add(prod)
        session.commit()
        session.refresh(prod)
        return prod


def _crear_cliente_real(id_document: str, nombre: str) -> Customer:
    with SessionManager() as session:
        cust = Customer(id_document=id_document, name=nombre)
        session.add(cust)
        session.commit()
        session.refresh(cust)
        return cust


# ── ALFA 1: login real → dashboard ─────────────────────────────────


class TestAlfaLoginYDashboard:
    def test_login_ui_abre_main_window_con_dashboard(
        self, qapp, mocker, logged_admin: UserSession, fake_rate, modal_dialogs
    ) -> None:
        window = LoginWindow()
        window.show()
        window._username_input.setText(ADMIN_USER)
        window._password_input.setText(ADMIN_PASS)
        window._login_btn.click()

        mains = [
            w
            for w in QApplication.topLevelWidgets()
            if isinstance(w, MainWindow) and w.isVisible()
        ]
        assert len(mains) == 1, "El login real debe abrir una MainWindow visible"
        main = mains[0]

        assert main.windowTitle() == "OpticaManager"
        assert main._stacked.currentIndex() == 0  # Dashboard
        assert len(main._nav_buttons) == 10
        msg = main.statusBar().currentMessage()
        assert "Admin Alfa" in msg

        # The real dashboard got built (page 0) and initialized its KPIs
        assert 0 in main._views
        main.close()


# ── ALFA 2: full real sale through the POS ──────────────────────────


class TestAlfaVentaCompletaPOS:
    def test_venta_completa_con_caja_producto_y_factura_real(
        self, qtbot, mocker, logged_admin: UserSession, fake_rate, modal_dialogs
    ) -> None:
        prod = _crear_producto_real("E2E-VENTA-001", "Lente Alfa E2E")
        cust = _crear_cliente_real("V-88888888", "Cliente Alfa E2E")
        assert prod.id is not None
        assert cust.id is not None

        # Navigate the real app: MainWindow → POS (index 5)
        main = MainWindow()
        qtbot.addWidget(main)
        main.show()
        main._nav_buttons[5].click()
        assert main._stacked.currentIndex() == 5
        assert 5 in main._views
        view = cast("POSView", main._views[5])

        # The cash session opened for REAL (dialog patched, service real)
        assert view._active_session is not None
        assert view._active_session.id is not None
        assert logged_admin.current_user is not None
        assert logged_admin.current_user.id is not None
        active = cash_session_service.get_active_session(logged_admin.current_user.id)
        assert active is not None and active.id == view._active_session.id

        # Cart holds the real product, added through the real table
        view._load_products()
        model = view._product_table.model()
        proxy = view._product_table.proxy()
        product_row = next(
            (
                row
                for row in range(proxy.rowCount())
                if model.item(proxy.mapToSource(proxy.index(row, 0)).row(), 0)
                and model.item(proxy.mapToSource(proxy.index(row, 0)).row(), 0).text()
                == str(prod.id)
            ),
            None,
        )
        assert product_row is not None, "El producto E2E debe aparecer en el catálogo"
        view._product_table.view().selectRow(product_row)
        view._product_table.view().setCurrentIndex(proxy.index(product_row, 0))
        view._add_selected_to_cart()
        spy_reload = mocker.spy(view, "_load_products")

        tab = view._active_tab()
        assert tab is not None
        assert len(tab.session.cart) == 1
        tab.session.customer = cust

        view._checkout()  # registrar_venta runs REAL against the isolated DB

        # Verify the sale in the DB: invoice, detail and decremented stock
        with SessionManager() as session:
            sale = session.exec(select(Sale).where(Sale.customer_id == cust.id)).first()
            assert sale is not None
            # The exact number depends on the prior DB state; what the test
            # checks is the format registrar_venta produces.
            assert re.fullmatch(r"FAC-\d{6}", sale.invoice_number)
            assert sale.total == Decimal("1044.00")  # 25 USD * 36 + 16% IVA
            assert sale.payment_method == "Efectivo Bs"
            assert sale.id is not None
            assert (
                session.exec(
                    select(SaleDetail).where(SaleDetail.sale_id == sale.id)
                ).first()
                is not None
            )
            prod_db = session.get(Product, prod.id)
            assert prod_db is not None
            assert prod_db.stock_quantity == 9  # 10 - 1

        spy_reload.assert_called()  # catalog refreshed after the sale
        assert tab.session.cart_empty()

        # Close the real cash session (dialog patched, service real)
        view._btn_close_session.click()
        assert view._active_session is None
        main.close()


# ── ALFA 3: full walk through every section ─────────────────────────


class TestAlfaRecorridoSecciones:
    def test_navegar_todas_las_secciones_sin_crash(
        self, qtbot, mocker, logged_admin: UserSession, fake_rate, modal_dialogs
    ) -> None:
        main = MainWindow()
        qtbot.addWidget(main)
        main.show()

        # 0 = Dashboard is already visible; walk the rest
        for i in range(1, 10):
            main._nav_buttons[i].click()
            assert main._stacked.currentIndex() == i
            assert len(main._views) >= i  # the view was built lazily

        # Back to the Dashboard: the already-built view refreshes without crashing
        main._nav_buttons[0].click()
        assert main._stacked.currentIndex() == 0
        main.close()
