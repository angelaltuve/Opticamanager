from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture
from pytestqt.qtbot import QtBot
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget

from opticamanager.core.session import UserData, UserSession
from opticamanager.ui.main_window import _LazyPage, MainWindow


@pytest.fixture(autouse=True)
def mock_all_views(mocker: MockerFixture) -> None:
    """Mock all views to avoid DB dependency. Each call returns a fresh QWidget.

    Views are lazy-loaded by MainWindow via importlib in ``_LazyPage._build``,
    so the mocks target the real module locations they resolve to.
    """
    targets = [
        "opticamanager.ui.views.dashboard_bi_view.DashboardBIView",
        "opticamanager.ui.views.inventario_view.InventarioView",
        "opticamanager.ui.views.categorias_view.CategoriasView",
        "opticamanager.ui.views.proveedores_view.ProveedoresView",
        "opticamanager.ui.views.clientes_view.ClientesView",
        "opticamanager.ui.views.pos_view.POSView",
        "opticamanager.ui.views.reportes_view.ReportesView",
        "opticamanager.ui.views.usuarios_view.UsuariosView",
        "opticamanager.ui.views.ajustes_view.SettingsView",
    ]
    for target in targets:
        mocker.patch(target, side_effect=QWidget)


@pytest.fixture(autouse=True)
def mock_user() -> UserData:
    """Set an authenticated user in UserSession for status bar."""
    user = UserData(
        id=1,
        username="admin",
        name="Admin User",
        email="admin@test.com",
        role_id=1,
        role_name="Admin",
    )
    UserSession._user = user
    return user


@pytest.fixture
def window(qtbot: QtBot, mock_all_views: None, mock_user: UserData) -> MainWindow:
    """Create a MainWindow instance for testing."""
    win = MainWindow()
    qtbot.add_widget(win)
    return win


class TestMainWindow:
    """Tests for MainWindow."""

    def test_main_window_title(self, window: MainWindow) -> None:
        """Window title should be 'OpticaManager'."""
        assert window.windowTitle() == "OpticaManager"

    def test_main_window_minimum_size(self, window: MainWindow) -> None:
        """Window should have minimum size 1000x650."""
        assert window.minimumWidth() == 1000
        assert window.minimumHeight() == 650

    def test_sidebar_has_ten_buttons(self, window: MainWindow) -> None:
        """Sidebar should contain exactly 10 nav buttons with correct text."""
        buttons = window._nav_buttons
        assert len(buttons) == 10
        expected_texts = [
            "📊  Dashboard",
            "📦  Inventario",
            "🏷️  Categorías",
            "🏢  Proveedores",
            "👥  Clientes",
            "🛒  POS",
            "📈  Reportes",
            "💰  Abonos",
            "👤  Usuarios",
            "⚙️  Ajustes",
        ]
        for btn, expected in zip(buttons, expected_texts):
            assert btn.text() == expected

    def test_initial_page_is_dashboard(self, window: MainWindow) -> None:
        """Stacked widget should start at index 0 and first button checked."""
        assert window._stacked.currentIndex() == 0
        assert window._nav_buttons[0].isChecked()

    def test_switch_to_inventario(self, window: MainWindow) -> None:
        """Clicking the "Inventario" button switches to page 1."""
        window._nav_buttons[1].click()
        assert window._stacked.currentIndex() == 1
        assert window._nav_buttons[1].isChecked()

    def test_switch_to_categorias(self, window: MainWindow) -> None:
        """Clicking the "Categorías" button switches to page 2."""
        window._nav_buttons[2].click()
        assert window._stacked.currentIndex() == 2
        assert window._nav_buttons[2].isChecked()

    def test_switch_to_proveedores(self, window: MainWindow) -> None:
        """Clicking the "Proveedores" button switches to page 3."""
        window._nav_buttons[3].click()
        assert window._stacked.currentIndex() == 3
        assert window._nav_buttons[3].isChecked()

    def test_switch_to_clientes(self, window: MainWindow) -> None:
        """Clicking the "Clientes" button switches to page 4."""
        window._nav_buttons[4].click()
        assert window._stacked.currentIndex() == 4
        assert window._nav_buttons[4].isChecked()

    def test_switch_to_pos(self, window: MainWindow) -> None:
        """Clicking POS button switches to page 5."""
        window._nav_buttons[5].click()
        assert window._stacked.currentIndex() == 5
        assert window._nav_buttons[5].isChecked()

    def test_switch_to_reportes(self, window: MainWindow) -> None:
        """Clicking the "Reportes" button switches to page 6."""
        window._nav_buttons[6].click()
        assert window._stacked.currentIndex() == 6
        assert window._nav_buttons[6].isChecked()

    def test_status_bar_shows_user(self, window: MainWindow) -> None:
        """Status bar should display user name and role."""
        message = window.statusBar().currentMessage()
        assert "Admin User" in message
        assert "Admin" in message

    def test_nav_buttons_exclusive(self, window: MainWindow) -> None:
        """Only one nav button should be checked at a time."""
        # Initial state: button 0 checked, others unchecked
        assert window._nav_buttons[0].isChecked()

        # Click button 1 - only it should be checked
        window._nav_buttons[1].click()
        assert window._nav_buttons[1].isChecked()
        assert not window._nav_buttons[0].isChecked()
        assert not window._nav_buttons[2].isChecked()
        assert not window._nav_buttons[3].isChecked()
        assert not window._nav_buttons[4].isChecked()
        assert not window._nav_buttons[5].isChecked()

        # Click button 3 - only it should be checked
        window._nav_buttons[3].click()
        assert window._nav_buttons[3].isChecked()
        assert not window._nav_buttons[0].isChecked()
        assert not window._nav_buttons[1].isChecked()
        assert not window._nav_buttons[2].isChecked()
        assert not window._nav_buttons[4].isChecked()
        assert not window._nav_buttons[5].isChecked()

    def test_sidebar_style(self, window: MainWindow) -> None:
        """Sidebar widget should have fixed width 200."""
        sidebar = window.centralWidget().layout().itemAt(0).widget()
        assert sidebar.minimumWidth() == 200
        assert sidebar.maximumWidth() == 200

    def test_lazy_page_is_replaced_on_show(
        self, qtbot: QtBot, window: MainWindow
    ) -> None:
        """Showing the window must hot-swap the first _LazyPage for the real view.

        Regression guard for a bug where the old code used the non-existent
        QStackedWidget.replaceWidget(); the placeholder must be replaced in place
        via insertWidget/removeWidget and cached so it is not rebuilt.
        """
        # Before show: page 0 is a _LazyPage, not yet built/cached.
        assert isinstance(window._stacked.widget(0), _LazyPage)
        assert 0 not in window._views

        window.show()
        qtbot.wait(30)

        view = window._views.get(0)
        assert view is not None
        assert window._stacked.widget(0) is view
        assert not isinstance(window._stacked.widget(0), _LazyPage)
        assert window._stacked.currentWidget() is view

    def test_switch_refresca_vista_construida(self, window: MainWindow) -> None:
        """Navigation must call the refresh hook on an already-built view."""
        view = MagicMock()
        window._views[1] = view
        window._nav_buttons[1].click()
        view._load_data.assert_called_once()

    def test_switch_refresca_dashboard(self, window: MainWindow) -> None:
        """The dashboard refresh hook must be its _refresh (charts + KPIs)."""
        view = MagicMock()
        window._views[0] = view
        window._nav_buttons[0].click()
        view._refresh.assert_called_once()

    def test_switch_no_refresca_vista_no_construida(self, window: MainWindow) -> None:
        """Pages not yet built (lazy) must not trigger a refresh call."""
        window._views.clear()
        window._nav_buttons[3].click()
        assert window._stacked.currentIndex() == 3
        assert 3 not in window._views

    def test_switch_vista_sin_hook_no_falla(self, window: MainWindow) -> None:
        """A built view missing the hook method is skipped without error."""
        view = MagicMock(spec=QWidget)  # has no _load_data / refresh method
        window._views[1] = view
        window._nav_buttons[1].click()
        assert window._stacked.currentIndex() == 1


def _vendedor(role_name: str | None = "Vendedor") -> UserData:
    return UserData(
        id=2,
        username="vendedor",
        name="Vendedor User",
        email="vendedor@test.com",
        role_id=2,
        role_name=role_name,
    )


@pytest.fixture
def vendedor_window(qtbot: QtBot, mock_all_views: None) -> MainWindow:
    """A MainWindow whose session belongs to a Vendedor."""
    UserSession._user = _vendedor()
    win = MainWindow()
    qtbot.add_widget(win)
    return win


class TestMainWindowVendedor:
    """Sidebar access for the Vendedor role, which is limited to the POS."""

    POS_INDEX = 5

    def test_solo_pos_visible(self, vendedor_window: MainWindow) -> None:
        """Only the POS button may be shown; the other nine stay hidden."""
        # The window is never shown, so isVisible() is False for every button
        # and carries no information: assert on isHidden() instead.
        shown = [
            i
            for i, btn in enumerate(vendedor_window._nav_buttons)
            if btn.isHidden() is False
        ]
        assert shown == [self.POS_INDEX]

    def test_texto_botones_conservado(self, vendedor_window: MainWindow) -> None:
        """Hiding a button must not alter the labels of the full sidebar."""
        assert vendedor_window._nav_buttons[self.POS_INDEX].text() == "🛒  POS"
        assert len(vendedor_window._nav_buttons) == 10

    def test_arranca_en_pos(self, vendedor_window: MainWindow) -> None:
        """The stack starts at index 0, which the Vendedor may not open."""
        assert vendedor_window._stacked.currentIndex() == self.POS_INDEX
        assert vendedor_window._nav_buttons[self.POS_INDEX].isChecked()

    def test_navegacion_bloqueada(self, vendedor_window: MainWindow) -> None:
        """Clicking a hidden button must not change the current section."""
        for hidden in (0, 1, 4, 6, 9):
            vendedor_window._nav_buttons[hidden].click()
            assert vendedor_window._stacked.currentIndex() == self.POS_INDEX

    def test_indice_inexistente_bloqueado(self, vendedor_window: MainWindow) -> None:
        """An out-of-range index must be rejected too, not raise."""
        vendedor_window._switch_page(42)
        assert vendedor_window._stacked.currentIndex() == self.POS_INDEX

    def test_vista_restringida_no_se_construye(
        self, qtbot: QtBot, vendedor_window: MainWindow
    ) -> None:
        """A blocked section must not replace its _LazyPage with the real view."""
        vendedor_window._nav_buttons[1].click()
        vendedor_window.show()
        qtbot.wait(30)
        assert isinstance(vendedor_window._stacked.widget(1), _LazyPage)
        assert 1 not in vendedor_window._views

    def test_cerrar_sesion_visible(self, vendedor_window: MainWindow) -> None:
        """The logout button stays reachable whatever the role."""
        sidebar = vendedor_window.centralWidget().layout().itemAt(0).widget()
        texts = [btn.text() for btn in sidebar.findChildren(QPushButton)]
        assert any("Cerrar Sesión" in t for t in texts)

    def test_rol_desconocido_falla_cerrado(
        self, qtbot: QtBot, mock_all_views: None
    ) -> None:
        """A role absent from the tables must not inherit the whole sidebar."""
        UserSession._user = _vendedor(role_name="Cajero")
        win = MainWindow()
        qtbot.add_widget(win)
        assert win._allowed_indices == {self.POS_INDEX}
        assert win._stacked.currentIndex() == self.POS_INDEX

    def test_usuario_sin_rol_no_ve_nada(
        self, qtbot: QtBot, mock_all_views: None
    ) -> None:
        """A NULL role_id must produce no sections, not the default fallback."""
        UserSession._user = _vendedor(role_name=None)
        win = MainWindow()
        qtbot.add_widget(win)
        assert win._allowed_indices == set()
        assert win._stacked.currentIndex() == 0
        label = win.centralWidget().findChild(QLabel, "no-access")
        assert label is not None
        assert "ninguna sección" in label.text()
