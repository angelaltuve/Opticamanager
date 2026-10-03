from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

from opticamanager.ui.views.categorias_view import CategoriasView


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_category(id_: int, name: str, description: str) -> MagicMock:
    """Build a mock object that looks like a Category model instance."""
    cat = MagicMock()
    cat.id = id_
    cat.name = name
    cat.description = description
    return cat


def _find_dialog(qtbot: QtBot) -> QDialog | None:  # noqa: F811
    """Return the first top-level QDialog, or *None*."""
    for w in QApplication.instance().topLevelWidgets():
        if isinstance(w, QDialog):
            return w
    return None


def _find_button(view: CategoriasView, text: str) -> QPushButton | None:
    """Locate a QPushButton whose exact text matches *text*."""
    for btn in view.findChildren(QPushButton):
        if btn.text() == text:
            return btn
    return None


def _select_first_row(view: CategoriasView, qtbot: QtBot) -> None:
    """Select the first *source* row via its proxy position.

    The proxy auto-sorts, so source row 0 may not be proxy row 0.
    We map from source to find the correct proxy row.
    """
    model = view._tabla.model()
    proxy = view._tabla.proxy()
    source_idx = model.index(0, 1)  # source row 0, column 1 ("Nombre")
    proxy_idx = proxy.mapFromSource(source_idx)
    rect = view._tabla.view().visualRect(proxy_idx)
    qtbot.mouseClick(
        view._tabla.view().viewport(),
        Qt.MouseButton.LeftButton,
        pos=rect.center(),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_category_service(mocker: MockerFixture) -> None:
    """Replace *category_service* functions with mocks; no real DB calls."""
    mocker.patch(
        "opticamanager.ui.views.categorias_view.list_categories",
        return_value=[
            _make_category(1, "Lentes", "Corrección visual"),
            _make_category(2, "Accesorios", "Estuches y limpiadores"),
        ],
    )
    mocker.patch(
        "opticamanager.ui.views.categorias_view.create_category",
        return_value=MagicMock(id=3),
    )
    mocker.patch("opticamanager.ui.views.categorias_view.update_category")
    mocker.patch(
        "opticamanager.ui.views.categorias_view.delete_category",
        return_value=True,
    )
    mocker.patch(
        "opticamanager.ui.views.categorias_view.dialogo_confirmacion",
        return_value=True,
    )


@pytest.fixture
def view(qtbot: QtBot, mock_category_service: None) -> CategoriasView:
    """Provide a fully-initialised *CategoriasView*."""
    v = CategoriasView()
    qtbot.addWidget(v)
    return v


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_creation_loads_data(view: CategoriasView) -> None:
    """View starts with two rows from the mocked *list_categories*."""
    assert view._tabla.model().rowCount() == 2


def test_columns_set_correctly(view: CategoriasView) -> None:
    """Column headers match expected labels."""
    model = view._tabla.model()
    assert model.headerData(0, Qt.Orientation.Horizontal) == "ID"
    assert model.headerData(1, Qt.Orientation.Horizontal) == "Nombre"
    assert model.headerData(2, Qt.Orientation.Horizontal) == "Descripción"


def test_nueva_btn_opens_dialog(qtbot: QtBot, view: CategoriasView) -> None:
    """Clicking ``+ Nueva Categoría`` opens a *QDialog*."""
    btn = _find_button(view, "+ Nueva Categoría")
    assert btn is not None

    dialogs_seen: list[bool] = []

    def _on_timer() -> None:
        dlg = _find_dialog(qtbot)
        dialogs_seen.append(dlg is not None)
        if dlg is not None:
            dlg.reject()

    QTimer.singleShot(200, _on_timer)
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
    qtbot.wait_until(lambda: len(dialogs_seen) > 0, timeout=2000)
    assert dialogs_seen[0] is True


def test_nueva_categoria_creates(
    qtbot: QtBot, mocker: MockerFixture, view: CategoriasView
) -> None:
    """Filling the dialog and accepting calls *create_category*."""
    mock_create = mocker.patch(
        "opticamanager.ui.views.categorias_view.create_category",
        return_value=MagicMock(id=3),
    )
    btn = _find_button(view, "+ Nueva Categoría")
    assert btn is not None

    def _fill_and_accept() -> None:
        dlg = _find_dialog(qtbot)
        if dlg is not None:
            dlg._name.setText("Nueva Cat")
            dlg._description.setText("Desc")
            dlg.accept()

    QTimer.singleShot(200, _fill_and_accept)
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)

    mock_create.assert_called_once_with(name="Nueva Cat", description="Desc")


def test_editar_categoria(
    qtbot: QtBot, mocker: MockerFixture, view: CategoriasView
) -> None:
    """Editing a selected row opens the dialog pre-filled with current values."""
    # Mock SessionManager used inside _editar_categoria to fetch the Category
    mock_session = MagicMock()
    mock_session.get.return_value = _make_category(1, "Lentes", "Corrección visual")
    mocker.patch(
        "opticamanager.ui.views.categorias_view.SessionManager",
    ).return_value.__enter__.return_value = mock_session

    _select_first_row(view, qtbot)
    btn = _find_button(view, "Editar")
    assert btn is not None

    dialog_seen: list[QDialog | None] = [None]

    def _check_and_close() -> None:
        dlg = _find_dialog(qtbot)
        dialog_seen[0] = dlg
        if dlg is not None:
            assert dlg._name.text() == "Lentes"
            assert dlg._description.text() == "Corrección visual"
            dlg.reject()

    QTimer.singleShot(200, _check_and_close)
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
    qtbot.wait_until(lambda: dialog_seen[0] is not None, timeout=2000)
    assert dialog_seen[0] is not None


def test_eliminar_categoria(
    qtbot: QtBot, mocker: MockerFixture, view: CategoriasView
) -> None:
    """Deleting a selected category calls *delete_category* with the correct ID."""
    # Mock SessionManager; no associated products, so deletion proceeds
    mock_session = MagicMock()
    mock_session.exec.return_value.all.return_value = []
    mocker.patch(
        "opticamanager.ui.views.categorias_view.SessionManager",
    ).return_value.__enter__.return_value = mock_session

    mock_delete = mocker.patch(
        "opticamanager.ui.views.categorias_view.delete_category",
        return_value=True,
    )

    _select_first_row(view, qtbot)
    btn = _find_button(view, "Eliminar")
    assert btn is not None
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)

    mock_delete.assert_called_once_with(1)


def test_eliminar_without_selection(
    qtbot: QtBot, mocker: MockerFixture, view: CategoriasView
) -> None:
    """Clicking "Eliminar" with no selection does NOT call *delete_category*."""
    mock_delete = mocker.patch(
        "opticamanager.ui.views.categorias_view.delete_category",
    )

    btn = _find_button(view, "Eliminar")
    assert btn is not None

    def _dismiss_message() -> None:
        for w in QApplication.instance().topLevelWidgets():
            if isinstance(w, QMessageBox):
                w.accept()

    QTimer.singleShot(200, _dismiss_message)
    qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)

    mock_delete.assert_not_called()
