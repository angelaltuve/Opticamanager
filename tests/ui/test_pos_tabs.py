"""Tests for parallel-sale POS tabs: _CartSession isolation and _SaleTab construction.

These target the pure-data parts (no DB) so they run headless without a session.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterator

import pytest
from PyQt6.QtWidgets import QApplication, QPushButton, QTableWidget

from opticamanager.services.settings_service import get_iva_rate, get_iva_rate_pct
from opticamanager.ui.views.pos_view import _CartItem, _CartSession, _SaleTab


@pytest.fixture(scope="module")
def qapp() -> Iterator[object]:
    """Module-scoped QApplication so widgets can be created without qtbot."""
    app = QApplication.instance() or QApplication([])
    yield app


def _item(price: str, qty: int = 1) -> _CartItem:
    return _CartItem(
        product_id=1,
        name="Test",
        unit_price=Decimal(price),
        unit_price_usd=Decimal(price),
        quantity=qty,
    )


def test_cart_session_starts_empty(qapp) -> None:
    s = _CartSession()
    assert s.cart_empty() is True
    assert s.customer is None
    assert s.prescription is None
    assert s.subtotal() == Decimal("0.00")


def test_cart_session_totals_compute_subtotal_iva(qapp) -> None:
    s = _CartSession()
    s.cart.append(_item("100.00"))
    s.cart.append(_item("50.00", qty=3))  # 150.00
    assert s.subtotal() == Decimal("250.00")
    iva = (Decimal("250.00") * get_iva_rate()).quantize(Decimal("0.01"))
    assert s.iva() == iva
    assert s.total() == Decimal("250.00") + iva


def test_cart_session_total_uses_subtotal_plus_iva(qapp) -> None:
    s = _CartSession()
    s.cart.append(_item("200.00"))
    assert s.total() == (s.subtotal() + s.iva()).quantize(Decimal("0.01"))


def test_parallel_sessions_are_isolated(qapp) -> None:
    """Two tabs must not share cart/customer state (parallel sales)."""
    s1 = _CartSession()
    s2 = _CartSession()
    s1.cart.append(_item("100.00"))
    assert s1.cart_empty() is False
    assert s2.cart_empty() is True
    assert s1.subtotal() == Decimal("100.00")
    assert s2.subtotal() == Decimal("0.00")


def test_cart_session_quantity_subtotal_rounds_half_up(qapp) -> None:
    s = _CartSession()
    s.cart.append(_item("33.333", qty=1))
    assert s.cart[0].subtotal == Decimal("33.33")


def test_sale_tab_constructs_with_empty_cart_and_controls(qapp) -> None:
    tab = _SaleTab()
    assert isinstance(tab.session, _CartSession)
    assert tab.session.cart_empty() is True
    assert tab.customer_edit.placeholderText() != ""
    assert tab.customer_edit.isVisible() is False  # inside never-shown widget
    assert isinstance(tab.cart_table, QTableWidget)
    assert tab.cart_table.columnCount() == 5
    assert isinstance(tab.btn_checkout, QPushButton)
    assert isinstance(tab.btn_clear, QPushButton)
    assert tab.subtotal_label.text() == "Bs. 0,00"
    assert tab.total_usd_label.text() == "$ 0,00"
    # Prescription buttons hidden until a customer is selected
    assert tab.btn_pick_rx.isVisible() is False
    assert tab.btn_rx_history.isVisible() is False


def test_sale_tab_iva_label_is_a_amount_label(qapp) -> None:
    tab = _SaleTab()
    # The IVA percentage lives in the form row label (not directly accessible);
    # the amount widget itself shows the computed IVA value, initially Bs. 0,00.
    assert tab.iva_label.text() == "Bs. 0,00"
    assert get_iva_rate_pct() >= 0
