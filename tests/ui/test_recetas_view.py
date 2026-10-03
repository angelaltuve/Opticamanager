"""Tests for RecetasDialog and PrescriptionFormDialog (recetas_view.py)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot
from PyQt6.QtCore import QDate, Qt

from opticamanager.ui.views.recetas_view import PrescriptionFormDialog, RecetasDialog


class _Result:
    """Chainable result mimicking ``session.exec(...)`` return values."""

    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return self._rows

    def one(self):
        return self._rows[0] if self._rows else None


def _make_customer() -> MagicMock:
    c = MagicMock()
    c.id = 1
    c.name = "Ana"
    c.id_document = "V-1"
    return c


def _make_rx(id_: int, issued: date) -> MagicMock:
    rx = MagicMock()
    rx.id = id_
    rx.customer_id = 1
    rx.issued_date = issued
    rx.od_sphere = Decimal("-1.50")
    rx.od_cylinder = Decimal("-0.25")
    rx.od_axis = 180
    rx.od_addition = None
    rx.os_sphere = Decimal("-2.00")
    rx.os_cylinder = None
    rx.os_axis = None
    rx.os_addition = None
    rx.pupillary_distance = Decimal("62.00")
    rx.notes = "Nota de prueba"
    return rx


# ---------------------------------------------------------------------------
# PrescriptionFormDialog (form, no DB)
# ---------------------------------------------------------------------------


def test_prescription_form_get_data_roundtrip(qtbot: QtBot) -> None:
    dlg = PrescriptionFormDialog(customer=_make_customer())
    dlg._od_sphere.setValue(-1.50)
    dlg._od_cylinder.setValue(-0.25)
    dlg._od_axis.setValue(180)
    dlg._os_sphere.setValue(-2.00)
    dlg._pupillary_distance.setValue(62.00)
    dlg._issued_date.setDate(QDate(2026, 9, 3))
    dlg._notes.setPlainText("Nota")

    data = dlg.get_data()

    assert data["customer_id"] == 1
    assert data["od_sphere"] == Decimal("-1.50")
    assert data["od_cylinder"] == Decimal("-0.25")
    assert data["od_axis"] == 180
    assert data["od_addition"] is None  # 0.00 -> None
    assert data["os_sphere"] == Decimal("-2.00")
    assert data["os_cylinder"] is None
    assert data["os_axis"] is None  # 0 -> None
    assert data["pupillary_distance"] == Decimal("62.00")
    assert data["issued_date"] == date(2026, 9, 3)
    assert data["notes"] == "Nota"


def test_prescription_form_edit_prefills(qtbot: QtBot) -> None:
    rx = _make_rx(7, date(2026, 1, 15))
    dlg = PrescriptionFormDialog(prescription=rx)

    assert dlg._od_sphere.value() == -1.50
    assert dlg._od_cylinder.value() == -0.25
    assert dlg._od_axis.value() == 180
    assert dlg._os_sphere.value() == -2.00
    assert dlg._pupillary_distance.value() == 62.00
    assert dlg._notes.toPlainText() == "Nota de prueba"
    assert dlg._issued_date.date().toPyDate() == date(2026, 1, 15)


# ---------------------------------------------------------------------------
# RecetasDialog rendering
# ---------------------------------------------------------------------------


def test_recetas_dialog_loads_rows(qtbot: QtBot, mocker: MockerFixture) -> None:
    mock_session = MagicMock()
    mock_session.exec.return_value.all.return_value = [_make_rx(7, date(2026, 1, 15))]
    mocker.patch(
        "opticamanager.ui.views.recetas_view.SessionManager"
    ).return_value.__enter__.return_value = mock_session

    dlg = RecetasDialog(_make_customer())
    qtbot.addWidget(dlg)

    assert dlg._tabla.model().rowCount() == 1
    assert dlg._tabla.model().headerData(0, Qt.Orientation.Horizontal) == "ID"
    # "Notas" truncated to 50 chars; our short note is preserved.
    assert dlg._tabla.model().item(0, 9).text() == "Nota de prueba"
