"""Tests for ClientesView and CustomerDialog (clientes_view.py)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

from opticamanager.ui.views.clientes_view import ClientesView, CustomerDialog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Result:
    """Chainable result mimicking ``session.exec(...)`` return values."""

    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return self._rows

    def one(self):
        return self._rows[0] if self._rows else None


def _make_customer(id_: int, doc: str, name: str) -> MagicMock:
    c = MagicMock()
    c.id = id_
    c.id_document = doc
    c.name = name
    c.phone = "04141234567"
    c.email = "a@b.c"
    c.address = "Calle 1"
    return c


def _find_dialog(qtbot: QtBot) -> QDialog | None:
    for w in QApplication.instance().topLevelWidgets():
        if isinstance(w, QDialog):
            return w
    return None


def _find_button(view: ClientesView, text: str):
    for btn in view.findChildren(QPushButton):
        if btn.text() == text:
            return btn
    return None


@pytest.fixture(autouse=True)
def _no_db(mocker: MockerFixture):
    """Stub SessionManager so the view never touches a real database."""
    mocker.patch("opticamanager.ui.views.clientes_view.SessionManager")


# ---------------------------------------------------------------------------
# CustomerDialog (form, no DB)
# ---------------------------------------------------------------------------


def test_customer_dialog_get_data_roundtrip(qtbot: QtBot) -> None:
    dlg = CustomerDialog()
    dlg._doc.setText("V-12345678")
    dlg._name.setText("Juan Pérez")
    dlg._phone.setText("04141234567")
    dlg._email.setText("juan@example.com")
    dlg._address.setText("Av. Principal")
    data = dlg.get_data()
    assert data == {
        "id_document": "V-12345678",
        "name": "Juan Pérez",
        "phone": "04141234567",
        "email": "juan@example.com",
        "address": "Av. Principal",
    }


def test_customer_dialog_invalid_data_becomes_none(qtbot: QtBot) -> None:
    dlg = CustomerDialog()
    dlg._doc.setText("V-12345678")
    dlg._name.setText("Solo Nombre")
    data = dlg.get_data()
    assert data["phone"] is None
    assert data["email"] is None
    assert data["address"] is None


# ---------------------------------------------------------------------------
# ClientesView rendering
# ---------------------------------------------------------------------------


def test_view_renders_customer_rows(qtbot: QtBot, mocker: MockerFixture) -> None:
    mock_session = MagicMock()
    mock_session.exec.side_effect = [
        _Result([_make_customer(1, "V-1", "Ana"), _make_customer(2, "V-2", "Luis")]),
        _Result([(1, 3), (2, 0)]),
    ]
    mocker.patch(
        "opticamanager.ui.views.clientes_view.SessionManager"
    ).return_value.__enter__.return_value = mock_session

    view = ClientesView()
    qtbot.addWidget(view)

    assert view._tabla.model().rowCount() == 2
    assert view._tabla.model().headerData(1, Qt.Orientation.Horizontal) == "Cédula"
    assert view._tabla.model().headerData(6, Qt.Orientation.Horizontal) == "Recetas"
    # Row 0 renders its prescription count (from the counts query)
    assert view._tabla.model().item(0, 6).text() == "3"
    assert view._tabla.model().item(1, 6).text() == "0"


# ---------------------------------------------------------------------------
# Create / delete behavior
# ---------------------------------------------------------------------------


class _FakeCustomerDialog:
    """Deterministic stand-in for CustomerDialog.

    Replaces the modal class entirely so no blocking ``exec()`` event loop
    ever runs (that pattern hangs in offscreen/headless environments).
    """

    def __init__(self, *args, **kwargs) -> None:
        self._doc = MagicMock()
        self._name = MagicMock()

    def exec(self) -> int:
        return QDialog.DialogCode.Accepted

    def get_data(self) -> dict:
        return {
            "id_document": "V-99999999",
            "name": "Nuevo Cliente",
            "phone": "04141234567",
            "email": None,
            "address": None,
        }


def test_new_client_saves_via_session(qtbot: QtBot, mocker: MockerFixture) -> None:
    mock_session = MagicMock()
    # __init__ -> _load_data (customer + prescription counts), then _load_data
    # again after creating the customer. Return the same empty result for every
    # exec call instead of counting them (avoids StopIteration -> modal error
    # dialog that hangs in offscreen/headless environments).
    mock_session.exec.return_value = _Result([])
    mocker.patch(
        "opticamanager.ui.views.clientes_view.SessionManager"
    ).return_value.__enter__.return_value = mock_session

    # No modal dialog: the view now builds the fake and always "accepts".
    mocker.patch(
        "opticamanager.ui.views.clientes_view.CustomerDialog", _FakeCustomerDialog
    )

    view = ClientesView()
    qtbot.addWidget(view)

    button = _find_button(view, "+ Nuevo Cliente")
    assert button is not None

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    qtbot.wait_until(lambda: mock_session.add.called, timeout=2000)

    # A new Customer was added to the mocked session.
    added = mock_session.add.call_args_list
    assert len(added) >= 1
    assert added[0].args[0].name == "Nuevo Cliente"


def test_delete_blocked_when_client_has_history(
    qtbot: QtBot, mocker: MockerFixture
) -> None:
    mock_session = MagicMock()
    mock_session.get.return_value = _make_customer(1, "V-1", "Ana")
    # deletion branch queries:
    #   exec(... rx count ...).one()  -> 1   (has prescriptions)
    #   exec(... sale count ...).one() -> 0
    mock_session.exec.side_effect = [_Result([1]), _Result([0])]
    mocker.patch(
        "opticamanager.ui.views.clientes_view.SessionManager"
    ).return_value.__enter__.return_value = mock_session
    mock_confirm = mocker.patch(
        "opticamanager.ui.views.clientes_view.dialogo_confirmacion"
    )

    # Avoid hitting the DB during __init__ (_load_data), then seed a row so
    # _selected_customer_id() resolves to customer 1.
    mocker.patch.object(ClientesView, "_load_data")
    view = ClientesView()
    qtbot.addWidget(view)
    view._tabla.add_row(["1", "V-1", "Ana", "—", "—", "—", "1"])

    model = view._tabla.model()
    proxy = view._tabla.proxy()
    prx = proxy.mapFromSource(model.index(0, 0))
    rect = view._tabla.view().visualRect(prx)
    qtbot.mouseClick(
        view._tabla.view().viewport(),
        Qt.MouseButton.LeftButton,
        pos=rect.center(),
    )

    button = _find_button(view, "Eliminar")
    assert button is not None

    def _dismiss() -> None:
        for w in QApplication.instance().topLevelWidgets():
            if isinstance(w, QMessageBox):
                w.accept()

    QTimer.singleShot(100, _dismiss)
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    qtbot.wait_until(lambda: mock_confirm.called or True, timeout=500)

    # History exists -> deletion must NOT be confirmed nor session.delete called.
    mock_confirm.assert_not_called()
    mock_session.delete.assert_not_called()
