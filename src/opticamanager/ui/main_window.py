from __future__ import annotations

from datetime import datetime
from typing import Final

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from opticamanager.core.logging_config import get_logger
from opticamanager.core.session import UserSession

log = get_logger(__name__)


class _SidebarButton(QPushButton):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("sidebar-btn")
        self.setCheckable(True)


class _LazyPage(QWidget):
    """Placeholder page that builds the real view on first activation.

    Delays both the import and construction of heavy views (e.g. POS)
    until the user actually navigates to them, improving startup time.
    """

    def __init__(
        self,
        main: MainWindow,
        provider: tuple[str, str],
        index: int,
        stacked: QStackedWidget,
    ) -> None:
        super().__init__()
        self._main = main
        self._provider = provider
        self._index = index
        self._stacked = stacked
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Cargando…"), alignment=Qt.AlignmentFlag.AlignCenter)
        self.setLayout(layout)

    def _build(self) -> QWidget:
        import importlib  # noqa: PLC0415

        module_name, class_name = self._provider
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        return cls()

    def showEvent(self, a0) -> None:  # noqa: N802
        """On first show, replace this placeholder with the real view."""
        super().showEvent(a0)
        if self._provider and self._index not in self._main._views:
            view = self._build()
            self._main._views[self._index] = view
            # QStackedWidget has no replaceWidget(); insert in place then drop
            # the placeholder (indexOf/insertWidget/removeWidget are valid API).
            idx = self._stacked.indexOf(self)
            self._stacked.insertWidget(idx, view)
            self._stacked.removeWidget(self)
            self._stacked.setCurrentWidget(view)
            self.deleteLater()


class _PlaceholderPage(QWidget):
    def __init__(self, title: str) -> None:
        super().__init__()
        layout = QVBoxLayout()
        layout.addWidget(QLabel(title), alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(
            QLabel("En construcción"),
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        self.setLayout(layout)


# ── Section registry ──
# Permissions below reference section names, never list positions, so
# reordering the sidebar cannot silently grant or revoke access to a role.
_SECTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("Dashboard", "📊"),
    ("Inventario", "📦"),
    ("Categorías", "🏷️"),
    ("Proveedores", "🏢"),
    ("Clientes", "👥"),
    ("POS", "🛒"),
    ("Reportes", "📈"),
    ("Abonos", "💰"),
    ("Usuarios", "👤"),
    ("Ajustes", "⚙️"),
)

_VIEW_PROVIDERS: Final[dict[int, tuple[str, str]]] = {
    0: ("opticamanager.ui.views.dashboard_bi_view", "DashboardBIView"),
    1: ("opticamanager.ui.views.inventario_view", "InventarioView"),
    2: ("opticamanager.ui.views.categorias_view", "CategoriasView"),
    3: ("opticamanager.ui.views.proveedores_view", "ProveedoresView"),
    4: ("opticamanager.ui.views.clientes_view", "ClientesView"),
    5: ("opticamanager.ui.views.pos_view", "POSView"),
    6: ("opticamanager.ui.views.reportes_view", "ReportesView"),
    7: ("opticamanager.ui.views.abonos_view", "AbonosView"),
    8: ("opticamanager.ui.views.usuarios_view", "UsuariosView"),
    9: ("opticamanager.ui.views.ajustes_view", "SettingsView"),
}

# Roles that reach every section without being listed section by section.
_FULL_ACCESS_ROLES: Final[frozenset[str]] = frozenset({"Admin"})

# Sections each role may open, by section name.
_ROLE_VISIBLE_SECTIONS: Final[dict[str, frozenset[str]]] = {
    "Vendedor": frozenset({"POS"}),
}

# Fallback for a role in neither table above. A role created straight in the
# database must not inherit the whole sidebar, so it gets the seller minimum.
_DEFAULT_VISIBLE_SECTIONS: Final[frozenset[str]] = frozenset({"POS"})


def _allowed_section_indices(role_name: str | None) -> set[int]:
    """Resolve the section positions a role may open.

    A role that is neither full access nor listed gets the default sections,
    and a user with no role at all (``role_id`` NULL) gets nothing: the check
    fails closed instead of handing the sidebar to an unexpected role name.
    """
    if role_name is None:
        return set()
    if role_name in _FULL_ACCESS_ROLES:
        return set(range(len(_SECTIONS)))
    names = _ROLE_VISIBLE_SECTIONS.get(role_name, _DEFAULT_VISIBLE_SECTIONS)
    return {i for i, (name, _) in enumerate(_SECTIONS) if name in names}


# Refresh hook per section index: method called on the already-built view every
# time its page becomes current, so data (including dashboard charts) stays up
# to date after changes made elsewhere (e.g. a sale in the POS).
_VIEW_REFRESH_HOOK: dict[int, str] = {
    0: "_refresh",  # DashboardBIView: KPIs + charts
    1: "_load_data",  # InventarioView
    2: "_load_data",  # CategoriasView
    3: "_load_data",  # ProveedoresView
    4: "_load_data",  # ClientesView
    5: "_load_products",  # POSView: product catalog + stock
    6: "_generate_report",  # ReportesView
    7: "_load_pendientes",  # AbonosView
    8: "_load_data",  # UsuariosView
    9: "_load_settings",  # SettingsView
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        if not UserSession().is_authenticated:
            QMessageBox.critical(self, "Error", "Acceso denegado. Debe iniciar sesión.")
            self.close()
            return

        self.setWindowTitle("OpticaManager")
        self.setMinimumSize(1000, 650)

        user = UserSession().current_user
        role_name = user.role_name if user else None
        self._allowed_indices = _allowed_section_indices(role_name)
        if not self._allowed_indices:
            log.warning("sin_secciones_para_rol role=%s", role_name)

        self._setup_ui()
        self._show_user_in_status_bar()

    def _setup_ui(self) -> None:
        sidebar = QVBoxLayout()
        sidebar.setContentsMargins(0, 0, 0, 0)
        sidebar.setSpacing(0)

        header_widget = QWidget()
        header_widget.setObjectName("sidebar-header")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 12, 0, 8)
        header_layout.setSpacing(2)

        logo = QLabel("OpticaManager")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setObjectName("sidebar-logo")
        header_layout.addWidget(logo)

        logo_sub = QLabel("Sistema de Gestión")
        logo_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_sub.setObjectName("sidebar-logo-sub")
        header_layout.addWidget(logo_sub)

        sidebar.addWidget(header_widget)

        self._stacked = QStackedWidget()

        self._views: dict[int, QWidget] = {}
        self._nav_buttons: list[_SidebarButton] = []

        # Every section keeps its stack index so the index stays the identity of
        # the section; a role that may not open one never reaches it, and its
        # lazy view is never built.
        for i, (name, icon) in enumerate(_SECTIONS):
            btn = _SidebarButton(f"{icon}  {name}")
            btn.clicked.connect(lambda checked, idx=i: self._switch_page(idx))
            btn.setVisible(i in self._allowed_indices)
            sidebar.addWidget(btn)
            self._nav_buttons.append(btn)

            provider = _VIEW_PROVIDERS.get(i, ("", ""))
            if provider[0]:
                self._stacked.addWidget(_LazyPage(self, provider, i, self._stacked))
            else:
                self._stacked.addWidget(_PlaceholderPage(name))

        # ── Logout button ──
        logout_btn = _SidebarButton("🚪  Cerrar Sesión")
        logout_btn.setProperty("logout", "true")
        logout_btn.style().unpolish(logout_btn)
        logout_btn.style().polish(logout_btn)
        logout_btn.clicked.connect(self._on_logout)
        sidebar.addWidget(logout_btn)

        sidebar.addStretch()

        sidebar_widget = QWidget()
        sidebar_widget.setLayout(sidebar)
        sidebar_widget.setFixedWidth(200)
        sidebar_widget.setObjectName("sidebar")

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(sidebar_widget)
        if self._allowed_indices:
            main_layout.addWidget(self._stacked, stretch=1)
        else:
            no_access = QLabel("Su rol no tiene acceso a ninguna sección.")
            no_access.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_access.setObjectName("no-access")
            main_layout.addWidget(no_access, stretch=1)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Open the first section the role may use. The stack starts at index 0,
        # which is hidden for every restricted role, so setting the page first
        # keeps the checked button and the visible page in sync.
        self._switch_page(min(self._allowed_indices, default=0))

    def _switch_page(self, index: int) -> None:
        """Show the section at ``index``, ignoring sections the role lacks.

        Hidden buttons stay in ``_nav_buttons`` and reachable through Qt, so the
        check belongs here and not only in the sidebar construction loop.
        """
        if index not in self._allowed_indices:
            user = UserSession().current_user
            log.warning(
                "acceso_denegado_seccion role=%s indice=%d",
                user.role_name if user else None,
                index,
            )
            return
        self._stacked.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)
        self._refresh_page_view(index)

    def _refresh_page_view(self, index: int) -> None:
        """Reload the current view's data when navigating to it (if already built).

        Views are constructed lazily on first show and load their own data in
        their __init__; only revisits need an explicit refresh. The hook method
        is looked up defensively so views without one are simply skipped.
        """
        hook = _VIEW_REFRESH_HOOK.get(index)
        if hook is None:
            return
        view = self._views.get(index)
        if view is None:
            return
        refresh = getattr(view, hook, None)
        if callable(refresh):
            refresh()

    def _show_user_in_status_bar(self) -> None:
        user = UserSession().current_user
        if user:
            now = datetime.now().strftime("%d/%m/%Y %H:%M")
            self.statusBar().showMessage(
                f"Usuario: {user.name} ({user.role_name})  |  {now}"
            )

    def _on_logout(self) -> None:
        UserSession().logout()
        self.close()
        from opticamanager.ui.login_window import LoginWindow  # noqa: PLC0415

        self._login_window = LoginWindow()
        self._login_window.show()


__all__ = ["MainWindow"]
