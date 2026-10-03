"""Unit tests for the POS payment dialog (_PaymentDialog)."""

from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from opticamanager.ui.views.pos_view import (
    EFECTIVO_BS,
    EFECTIVO_USD,
    MIXTO,
    PAGO_MOVIL,
    ZELLE,
    PAYMENT_METHOD_CHOICES,
    _PaymentDialog,
)


def _open_dialog(qtbot: QtBot, total: Decimal, total_usd: Decimal | None = None):
    dlg = _PaymentDialog(total=total, total_usd=total_usd)
    qtbot.addWidget(dlg)
    return dlg


def test_defaults_to_pago_movil_and_preselects_total(qtbot: QtBot) -> None:
    """Dialogs default to the first listed method and pre-fill the total."""
    dlg = _open_dialog(qtbot, Decimal("150.00"))
    assert PAYMENT_METHOD_CHOICES[0] == PAGO_MOVIL
    assert dlg.payment_method == PAGO_MOVIL
    assert dlg._received_spin.value() == 150.00


def test_efectivo_bs_change_autocomputed(qtbot: QtBot) -> None:
    """Change = received - total when receiving cash in Bs."""
    dlg = _open_dialog(qtbot, Decimal("150.00"))
    dlg._method_combo.setCurrentText(EFECTIVO_BS)
    dlg._received_spin.setValue(200.00)
    assert "50" in dlg._change_label.text()
    assert "Bs." in dlg._change_label.text()

    # Below total -> change clamped to 0
    dlg._received_spin.setValue(100.00)
    assert "0" in dlg._change_label.text()


def test_efectivo_bs_accept_builds_single_bs_payment(qtbot: QtBot) -> None:
    """Accepting "Efectivo Bs" yields one Bs payment with the received amount."""
    dlg = _open_dialog(qtbot, Decimal("150.00"))
    dlg._method_combo.setCurrentText(EFECTIVO_BS)
    dlg._received_spin.setValue(200.00)
    dlg._validate_and_accept()
    assert dlg.result() == 1  # accepted
    assert dlg.payment_method == EFECTIVO_BS
    assert dlg.amount_received == Decimal("200.00")
    assert dlg.change_amount == Decimal("50.00")
    assert dlg.payments == [
        {
            "method": EFECTIVO_BS,
            "currency": "Bs",
            "amount": Decimal("200.00"),
            "amount_bs": Decimal("200.00"),
            "rate_used": None,
        }
    ]


def test_pago_movil_and_zelle_charge_full_total(qtbot: QtBot) -> None:
    """ "Pago Móvil" / "Zelle" record a single Bs payment equal to the total."""
    for method in (PAGO_MOVIL, ZELLE):
        dlg = _open_dialog(qtbot, Decimal("100.00"))
        dlg._method_combo.setCurrentText(method)
        assert not dlg._simple_label.isHidden()
        dlg._validate_and_accept()
        assert dlg.payment_method == method
        assert dlg.amount_received == Decimal("100.00")
        assert dlg.change_amount == Decimal("0")
        assert dlg.payments == [
            {
                "method": method,
                "currency": "Bs",
                "amount": Decimal("100.00"),
                "amount_bs": Decimal("100.00"),
                "rate_used": None,
            }
        ]


def test_efectivo_usd_preselects_usd_total(qtbot: QtBot) -> None:
    """ "Efectivo Dólares" pre-selects the USD equivalent when total_usd given."""
    dlg = _open_dialog(qtbot, Decimal("400.00"), total_usd=Decimal("10.00"))
    dlg._method_combo.setCurrentText(EFECTIVO_USD)
    assert dlg._received_spin.prefix() == "$ "
    assert dlg._received_spin.value() == 10.00


def test_mixto_opens_with_one_row_and_autocompletes_remaining(
    qtbot: QtBot,
) -> None:
    """Mixto starts with one Bs row auto-filled to the total."""
    dlg = _open_dialog(qtbot, Decimal("200.00"))
    dlg._method_combo.setCurrentText(MIXTO)
    assert len(dlg._mixed_rows) == 1
    row = dlg._mixed_rows[0]
    assert row.amount_spin.value() == 200.00
    assert "200" in dlg._mixto_total_label.text()


def test_mixto_two_rows_autofills_second_row(qtbot: QtBot) -> None:
    """When one row is set, adding another auto-fills the remaining in the last."""
    dlg = _open_dialog(qtbot, Decimal("100.00"))
    dlg._method_combo.setCurrentText(MIXTO)
    # First row holds the total by default; set it to simulate partial.
    dlg._mixed_rows[0].amount_spin.setValue(30.00)
    dlg._add_mixed_row()
    assert len(dlg._mixed_rows) == 2
    # The new last (Bs) row should be auto-filled with the remaining 70.
    assert dlg._mixed_rows[1].amount_spin.value() == 70.00
    # The balance row now covers the total.
    assert "Falta Bs. 0" in dlg._mixto_total_label.text()
    assert "100" in dlg._mixto_total_label.text()


def test_mixto_accept_builds_per_method_payments(qtbot: QtBot) -> None:
    """Mixto builds a payments list with one entry per non-empty row."""
    dlg = _open_dialog(qtbot, Decimal("100.00"))
    dlg._method_combo.setCurrentText(MIXTO)
    dlg._mixed_rows[0].method_combo.setCurrentText(EFECTIVO_BS)
    dlg._mixed_rows[0].amount_spin.setValue(40.00)
    dlg._add_mixed_row()
    dlg._mixed_rows[1].method_combo.setCurrentText(PAGO_MOVIL)
    dlg._mixed_rows[1].amount_spin.setValue(60.00)
    dlg._validate_and_accept()
    assert dlg.payment_method == MIXTO
    assert len(dlg.payments) == 2
    assert {p["method"] for p in dlg.payments} == {
        EFECTIVO_BS,
        PAGO_MOVIL,
    }
    for p in dlg.payments:
        assert p["currency"] == "Bs"
        assert p["amount_bs"] == p["amount"]
    assert dlg.amount_received == Decimal("100.00")
    assert dlg.change_amount == Decimal("0")


def test_efectivo_bs_rejects_insufficient_amount(qtbot: QtBot, monkeypatch) -> None:
    """Accepting with received < total warns and does not accept."""
    dlg = _open_dialog(qtbot, Decimal("150.00"))
    warned: list = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *a, **k: warned.append(str(a[1]) if len(a) > 1 else ""),
    )
    dlg._method_combo.setCurrentText(EFECTIVO_BS)
    dlg._received_spin.setValue(100.00)
    dlg._validate_and_accept()
    assert warned, "expected a warning"
    assert dlg.result() != 1  # not accepted


def test_mixto_rejects_undersum(qtbot: QtBot, monkeypatch) -> None:
    """Mixto with sum < total warns and does not accept."""
    dlg = _open_dialog(qtbot, Decimal("100.00"))
    warned: list = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *a, **k: warned.append(str(a[1]) if len(a) > 1 else ""),
    )
    dlg._method_combo.setCurrentText(MIXTO)
    dlg._mixed_rows[0].amount_spin.setValue(50.00)
    dlg._validate_and_accept()
    assert warned, "expected a warning"
    assert dlg.result() != 1


def test_remove_row_keeps_minimum_one(qtbot: QtBot) -> None:
    """Removing rows keeps at least one Mixto row."""
    dlg = _open_dialog(qtbot, Decimal("100.00"))
    dlg._method_combo.setCurrentText(MIXTO)
    first = dlg._mixed_rows[0]
    dlg._add_mixed_row()
    assert len(dlg._mixed_rows) == 2
    dlg._remove_mixed_row(first)
    assert len(dlg._mixed_rows) == 1
    dlg._remove_mixed_row(dlg._mixed_rows[0])
    assert len(dlg._mixed_rows) == 1  # can't drop the last one


def test_mixto_edit_earlier_row_rebalances_last(qtbot: QtBot) -> None:
    """Lowering an earlier row rebalances the last (non-USD) row with the rest."""
    dlg = _open_dialog(qtbot, Decimal("200.00"))
    dlg._method_combo.setCurrentText(MIXTO)
    dlg._mixed_rows[0].amount_spin.setValue(100.00)
    dlg._add_mixed_row()
    assert len(dlg._mixed_rows) == 2
    # Second row auto-filled with the remaining.
    assert dlg._mixed_rows[1].amount_spin.value() == 100.00
    # Lower the first row: the last row absorbs the new remaining (150).
    dlg._mixed_rows[0].amount_spin.setValue(50.00)
    assert dlg._mixed_rows[1].amount_spin.value() == 150.00
    assert dlg._sum_mixed_bs() == Decimal("200.00")


def test_mixto_manual_last_row_respected(qtbot: QtBot) -> None:
    """Editing the last (balance) row directly is respected; label shows gap."""
    dlg = _open_dialog(qtbot, Decimal("200.00"))
    dlg._method_combo.setCurrentText(MIXTO)
    dlg._mixed_rows[0].amount_spin.setValue(100.00)
    dlg._add_mixed_row()
    # Auto-filled to 100; the user then types 80 manually.
    dlg._mixed_rows[1].amount_spin.setValue(80.00)
    assert dlg._mixed_rows[1].amount_spin.value() == 80.00
    assert "20" in dlg._mixto_total_label.text()
