"""Tests for UsuariosView, _UserDialog and _PasswordDialog.

Coverage target: >=70% of usuarios_view.py
Strategy: mock the user_service functions and the dialogs to stay off the real DB.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from PyQt6.QtWidgets import (
    QDialog,
    QMessageBox,
)
from pytest_mock import MockerFixture

from opticamanager.core.session import UserSession, UserData
from opticamanager.ui.views.usuarios_view import (
    UsuariosView,
    _PasswordDialog,
    _UserDialog,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_user_for_table(
    user_id: int = 1,
    username: str = "admin",
    name: str = "Admin User",
    email: str = "admin@test.com",
    role_id: int = 1,
    role_name: str = "Admin",
    active: bool = True,
    created_at: datetime | None = None,
) -> MagicMock:
    """Create a mock User object for table display."""
    u = MagicMock()
    u.id = user_id
    u.username = username
    u.name = name
    u.email = email
    u.role_id = role_id
    u.active = active
    u.created_at = created_at or datetime(2026, 1, 15)
    u.role = MagicMock()
    u.role.name = role_name
    return u


def _make_role(role_id: int = 1, name: str = "Admin") -> MagicMock:
    r = MagicMock()
    r.id = role_id
    r.name = name
    return r


def _fake_user_session(
    mocker: MockerFixture,
    user_id: int = 1,
    role_name: str = "Admin",
) -> None:
    """Set up UserSession with a mock user."""
    user_data = UserData(
        id=user_id,
        username="admin",
        name="Admin User",
        email="admin@test.com",
        role_id=1,
        role_name=role_name,
    )
    UserSession._user = user_data


# ── _UserDialog Tests ────────────────────────────────────────────────────


class TestUserDialogCreacion:
    """Tests for _UserDialog creation and UI setup."""

    def test_creacion_nuevo_usuario(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_roles",
            return_value=[_make_role(1, "Admin"), _make_role(2, "Vendedor")],
        )
        dlg = _UserDialog()
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Nuevo Usuario"
        assert dlg._editing is False

    def test_creacion_editar_usuario(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_roles",
            return_value=[_make_role(1, "Admin")],
        )
        mock_user = MagicMock()
        mock_user.username = "admin"
        mock_user.name = "Admin User"
        mock_user.email = "admin@test.com"
        mock_user.role_id = 1
        mock_user.active = True
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.get_user",
            return_value=mock_user,
        )
        dlg = _UserDialog(user_id=1)
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Editar Usuario"
        assert dlg._editing is True
        assert dlg._username.text() == "admin"
        assert not dlg._username.isEnabled()

    def test_get_data_nuevo_usuario(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_roles",
            return_value=[_make_role(1, "Admin")],
        )
        dlg = _UserDialog()
        qtbot.addWidget(dlg)
        dlg._username.setText("newuser")
        dlg._name.setText("New User")
        dlg._email.setText("new@test.com")
        dlg._password.setText("password123")
        dlg._confirm.setText("password123")
        data = dlg.get_data()
        assert data["username"] == "newuser"
        assert data["name"] == "New User"
        assert data["email"] == "new@test.com"
        assert data["password"] == "password123"

    def test_get_data_editar_usuario(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_roles",
            return_value=[_make_role(1, "Admin")],
        )
        mock_user = MagicMock()
        mock_user.username = "admin"
        mock_user.name = "Admin"
        mock_user.email = "admin@test.com"
        mock_user.role_id = 1
        mock_user.active = True
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.get_user",
            return_value=mock_user,
        )
        dlg = _UserDialog(user_id=1)
        qtbot.addWidget(dlg)
        data = dlg.get_data()
        assert "password" not in data


class TestUserDialogValidacion:
    """Tests for _UserDialog._validate_and_accept."""

    def test_usuario_vacio_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_roles",
            return_value=[_make_role(1, "Admin")],
        )
        dlg = _UserDialog()
        qtbot.addWidget(dlg)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("ok"),
        )
        dlg._username.setText("")
        dlg._name.setText("Name")
        dlg._email.setText("a@b.com")
        dlg._password.setText("password123")
        dlg._confirm.setText("password123")
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_usuario_corto_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_roles",
            return_value=[_make_role(1, "Admin")],
        )
        dlg = _UserDialog()
        qtbot.addWidget(dlg)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("ok"),
        )
        dlg._username.setText("ab")
        dlg._name.setText("Name")
        dlg._email.setText("a@b.com")
        dlg._password.setText("password123")
        dlg._confirm.setText("password123")
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_nombre_vacio_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_roles",
            return_value=[_make_role(1, "Admin")],
        )
        dlg = _UserDialog()
        qtbot.addWidget(dlg)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("ok"),
        )
        dlg._username.setText("newuser")
        dlg._name.setText("")
        dlg._email.setText("a@b.com")
        dlg._password.setText("password123")
        dlg._confirm.setText("password123")
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_email_invalido_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_roles",
            return_value=[_make_role(1, "Admin")],
        )
        dlg = _UserDialog()
        qtbot.addWidget(dlg)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("ok"),
        )
        dlg._username.setText("newuser")
        dlg._name.setText("Name")
        dlg._email.setText("notanemail")
        dlg._password.setText("password123")
        dlg._confirm.setText("password123")
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_password_corto_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_roles",
            return_value=[_make_role(1, "Admin")],
        )
        dlg = _UserDialog()
        qtbot.addWidget(dlg)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("ok"),
        )
        dlg._username.setText("newuser")
        dlg._name.setText("Name")
        dlg._email.setText("a@b.com")
        dlg._password.setText("short")
        dlg._confirm.setText("short")
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_passwords_no_coinciden_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_roles",
            return_value=[_make_role(1, "Admin")],
        )
        dlg = _UserDialog()
        qtbot.addWidget(dlg)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("ok"),
        )
        dlg._username.setText("newuser")
        dlg._name.setText("Name")
        dlg._email.setText("a@b.com")
        dlg._password.setText("password123")
        dlg._confirm.setText("differentpassword")
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_validacion_ok_acepta(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_roles",
            return_value=[_make_role(1, "Admin")],
        )
        dlg = _UserDialog()
        qtbot.addWidget(dlg)
        dlg._username.setText("newuser")
        dlg._name.setText("Name")
        dlg._email.setText("a@b.com")
        dlg._password.setText("password123")
        dlg._confirm.setText("password123")
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted

    def test_editar_usuario_no_valida_password(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_roles",
            return_value=[_make_role(1, "Admin")],
        )
        mock_user = MagicMock()
        mock_user.username = "admin"
        mock_user.name = "Admin"
        mock_user.email = "admin@test.com"
        mock_user.role_id = 1
        mock_user.active = True
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.get_user",
            return_value=mock_user,
        )
        dlg = _UserDialog(user_id=1)
        qtbot.addWidget(dlg)
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted

    def test_load_user_no_encontrado_no_crash(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_roles",
            return_value=[_make_role(1, "Admin")],
        )
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.get_user",
            return_value=None,
        )
        dlg = _UserDialog(user_id=999)
        qtbot.addWidget(dlg)
        # Should not crash, username field stays empty
        assert dlg._username.text() == ""


# ── _PasswordDialog Tests ────────────────────────────────────────────────


class TestPasswordDialog:
    """Tests for _PasswordDialog."""

    def test_creacion(self, qtbot: QtBot) -> None:
        dlg = _PasswordDialog()
        qtbot.addWidget(dlg)
        assert dlg.windowTitle() == "Cambiar Contraseña"

    def test_password_corto_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        dlg = _PasswordDialog()
        qtbot.addWidget(dlg)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("ok"),
        )
        dlg._password.setText("short")
        dlg._confirm.setText("short")
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_passwords_no_coinciden_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        dlg = _PasswordDialog()
        qtbot.addWidget(dlg)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("ok"),
        )
        dlg._password.setText("password123")
        dlg._confirm.setText("different")
        dlg._validate_and_accept()
        assert warned
        assert dlg.result() != QDialog.DialogCode.Accepted

    def test_validacion_ok_acepta(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        dlg = _PasswordDialog()
        qtbot.addWidget(dlg)
        dlg._password.setText("password123")
        dlg._confirm.setText("password123")
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted

    def test_get_password(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        dlg = _PasswordDialog()
        qtbot.addWidget(dlg)
        dlg._password.setText("newpassword")
        assert dlg.get_password() == "newpassword"


# ── UsuariosView Tests ───────────────────────────────────────────────────


class TestUsuariosViewCreacion:
    """Smoke tests for UsuariosView creation."""

    def test_creacion_basica(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=[],
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        assert isinstance(view, UsuariosView)

    def test_titulo_visible(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=[],
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        from PyQt6.QtWidgets import QLabel

        titles = view.findChildren(QLabel, "title-h2")
        assert len(titles) >= 1
        assert "Usuarios" in titles[0].text()

    def test_botones_toolbar(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=[],
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        from PyQt6.QtWidgets import QPushButton

        buttons = view.findChildren(QPushButton)
        texts = [b.text() for b in buttons]
        assert any("Nuevo" in t for t in texts)
        assert any("Editar" in t for t in texts)
        assert any("Contraseña" in t for t in texts)
        assert any("Activar" in t for t in texts)
        assert any("Eliminar" in t for t in texts)


class TestUsuariosViewLoadData:
    """Tests for _load_data."""

    def test_load_data_vacio(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=[],
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        assert view._tabla.row_count() == 0

    def test_load_data_con_usuarios(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        users = [
            _make_user_for_table(1, "admin", "Admin", "a@t.com", 1, "Admin", True),
            _make_user_for_table(
                2, "vendedor", "Vendedor", "v@t.com", 2, "Vendedor", False
            ),
        ]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        assert view._tabla.row_count() == 2

    def test_usuario_inactivo_color_rojo(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        users = [
            _make_user_for_table(1, "user1", "User", "u@t.com", 2, "Vendedor", False),
        ]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        assert view._tabla.row_count() == 1
        # Check "No" in active column
        active_item = view._tabla.model().item(0, 5)
        assert active_item is not None
        assert active_item.text() == "No"

    def test_usuario_activo_color_verde(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        users = [
            _make_user_for_table(1, "user1", "User", "u@t.com", 2, "Vendedor", True),
        ]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        active_item = view._tabla.model().item(0, 5)
        assert active_item is not None
        assert active_item.text() == "Sí"

    def test_fecha_none_muestra_guion(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        user = _make_user_for_table()
        user.created_at = None
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=[user],
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        created_item = view._tabla.model().item(0, 6)
        assert created_item is not None
        assert created_item.text() == "\u2014"

    def test_rol_none_muestra_guion(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        users = [_make_user_for_table(role_name=None)]
        users[0].role = None
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        role_item = view._tabla.model().item(0, 4)
        assert role_item is not None
        assert role_item.text() == "—"


class TestUsuariosViewNuevoUsuario:
    """Tests for _nuevo_usuario flow."""

    def test_dialogo_cancelado_no_crea(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=[],
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.usuarios_view._UserDialog",
            return_value=mock_dlg,
        )
        view._nuevo_usuario()
        # No error, just returned

    def test_dialogo_aceptado_crea_usuario(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=[],
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_data.return_value = {
            "username": "newuser",
            "name": "New",
            "email": "n@t.com",
            "password": "pass1234",
            "role_id": 1,
            "active": True,
        }
        mocker.patch(
            "opticamanager.ui.views.usuarios_view._UserDialog",
            return_value=mock_dlg,
        )
        mock_create = mocker.patch(
            "opticamanager.ui.views.usuarios_view.create_user",
            return_value=None,
        )
        view._nuevo_usuario()
        mock_create.assert_called_once()

    def test_error_al_crear_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=[],
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_data.return_value = {
            "username": "newuser",
            "name": "New",
            "email": "n@t.com",
            "password": "pass1234",
            "role_id": 1,
            "active": True,
        }
        mocker.patch(
            "opticamanager.ui.views.usuarios_view._UserDialog",
            return_value=mock_dlg,
        )
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.create_user",
            return_value="Error de duplicado",
        )
        mock_error = mocker.patch(
            "opticamanager.ui.views.usuarios_view.dialogo_error",
        )
        view._nuevo_usuario()
        mock_error.assert_called_once()


class TestUsuariosViewEditarUsuario:
    """Tests for _editar_usuario flow."""

    def test_sin_seleccion_no_hace_nada(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=[],
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        msgs: list = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._editar_usuario()
        assert msgs

    def test_dialogo_cancelado_no_edita(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        users = [_make_user_for_table()]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.usuarios_view._UserDialog",
            return_value=mock_dlg,
        )
        view._editar_usuario()

    def test_dialogo_aceptado_edita_usuario(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        users = [_make_user_for_table()]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_data.return_value = {
            "username": "admin",
            "name": "Updated",
            "email": "u@t.com",
            "role_id": 1,
            "active": True,
        }
        mocker.patch(
            "opticamanager.ui.views.usuarios_view._UserDialog",
            return_value=mock_dlg,
        )
        mock_update = mocker.patch(
            "opticamanager.ui.views.usuarios_view.update_user",
            return_value=None,
        )
        view._editar_usuario()
        mock_update.assert_called_once()

    def test_error_al_editar_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        users = [_make_user_for_table()]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_data.return_value = {
            "username": "admin",
            "name": "Updated",
            "email": "u@t.com",
            "role_id": 1,
            "active": True,
        }
        mocker.patch(
            "opticamanager.ui.views.usuarios_view._UserDialog",
            return_value=mock_dlg,
        )
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.update_user",
            return_value="Error de edición",
        )
        mock_error = mocker.patch(
            "opticamanager.ui.views.usuarios_view.dialogo_error",
        )
        view._editar_usuario()
        mock_error.assert_called_once()


class TestUsuariosViewCambiarPassword:
    """Tests for _cambiar_password flow."""

    def test_sin_seleccion_no_hace_nada(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=[],
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        msgs: list = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._cambiar_password()
        assert msgs

    def test_dialogo_cancelado_no_cambia(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        users = [_make_user_for_table()]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Rejected
        mocker.patch(
            "opticamanager.ui.views.usuarios_view._PasswordDialog",
            return_value=mock_dlg,
        )
        view._cambiar_password()

    def test_dialogo_aceptado_cambia_password(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        users = [_make_user_for_table()]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_password.return_value = "newpassword123"
        mocker.patch(
            "opticamanager.ui.views.usuarios_view._PasswordDialog",
            return_value=mock_dlg,
        )
        mock_change = mocker.patch(
            "opticamanager.ui.views.usuarios_view.change_password",
            return_value=None,
        )
        info_msgs: list = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: info_msgs.append("ok"),
        )
        view._cambiar_password()
        mock_change.assert_called_once()
        assert info_msgs

    def test_error_al_cambiar_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        users = [_make_user_for_table()]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        mock_dlg = MagicMock()
        mock_dlg.exec.return_value = QDialog.DialogCode.Accepted
        mock_dlg.get_password.return_value = "newpassword123"
        mocker.patch(
            "opticamanager.ui.views.usuarios_view._PasswordDialog",
            return_value=mock_dlg,
        )
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.change_password",
            return_value="Error de password",
        )
        mock_error = mocker.patch(
            "opticamanager.ui.views.usuarios_view.dialogo_error",
        )
        view._cambiar_password()
        mock_error.assert_called_once()


class TestUsuariosViewToggleActivo:
    """Tests for _toggle_activo flow."""

    def test_sin_seleccion_no_hace_nada(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=[],
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        msgs: list = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._toggle_activo()
        assert msgs

    def test_no_puede_desactivar_self(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        _fake_user_session(mocker, user_id=1)
        users = [_make_user_for_table(user_id=1)]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        warned: list = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        view._toggle_activo()
        assert warned

    def test_cancelar_toggle(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_user_session(mocker, user_id=1)
        users = [_make_user_for_table(user_id=2)]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        mock_user = MagicMock()
        mock_user.id = 2
        mock_user.username = "user2"
        mock_user.active = True
        mock_user.name = "User2"
        mock_user.email = "u2@t.com"
        mock_user.role_id = 2
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.get_user",
            return_value=mock_user,
        )
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.dialogo_confirmacion",
            return_value=False,
        )
        view._toggle_activo()

    def test_toggle_exitoso(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_user_session(mocker, user_id=1)
        users = [_make_user_for_table(user_id=2)]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        mock_user = MagicMock()
        mock_user.id = 2
        mock_user.username = "user2"
        mock_user.active = True
        mock_user.name = "User2"
        mock_user.email = "u2@t.com"
        mock_user.role_id = 2
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.get_user",
            return_value=mock_user,
        )
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.dialogo_confirmacion",
            return_value=True,
        )
        mock_update = mocker.patch(
            "opticamanager.ui.views.usuarios_view.update_user",
            return_value=None,
        )
        view._toggle_activo()
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args
        assert call_kwargs[1]["active"] is False

    def test_error_al_toggle_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        _fake_user_session(mocker, user_id=1)
        users = [_make_user_for_table(user_id=2)]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        mock_user = MagicMock()
        mock_user.id = 2
        mock_user.username = "user2"
        mock_user.active = True
        mock_user.name = "User2"
        mock_user.email = "u2@t.com"
        mock_user.role_id = 2
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.get_user",
            return_value=mock_user,
        )
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.dialogo_confirmacion",
            return_value=True,
        )
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.update_user",
            return_value="Error al toggle",
        )
        mock_error = mocker.patch(
            "opticamanager.ui.views.usuarios_view.dialogo_error",
        )
        view._toggle_activo()
        mock_error.assert_called_once()

    def test_user_no_encontrado(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_user_session(mocker, user_id=1)
        users = [_make_user_for_table(user_id=2)]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.get_user",
            return_value=None,
        )
        view._toggle_activo()
        # Should return without crash


class TestUsuariosViewEliminarUsuario:
    """Tests for _eliminar_usuario flow."""

    def test_sin_seleccion_no_hace_nada(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=[],
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        msgs: list = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: msgs.append("info"),
        )
        view._eliminar_usuario()
        assert msgs

    def test_no_puede_eliminar_self(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_user_session(mocker, user_id=1)
        users = [_make_user_for_table(user_id=1)]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        warned: list = []
        mocker.patch.object(
            QMessageBox,
            "warning",
            side_effect=lambda *_a, **_k: warned.append("warn"),
        )
        view._eliminar_usuario()
        assert warned

    def test_cancelar_eliminacion(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_user_session(mocker, user_id=1)
        users = [_make_user_for_table(user_id=2)]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        mock_user = MagicMock()
        mock_user.id = 2
        mock_user.username = "user2"
        mock_user.active = True
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.get_user",
            return_value=mock_user,
        )
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.dialogo_confirmacion",
            return_value=False,
        )
        view._eliminar_usuario()

    def test_confirmar_eliminacion_exitosa(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        _fake_user_session(mocker, user_id=1)
        users = [_make_user_for_table(user_id=2)]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        mock_user = MagicMock()
        mock_user.id = 2
        mock_user.username = "user2"
        mock_user.active = True
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.get_user",
            return_value=mock_user,
        )
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.dialogo_confirmacion",
            return_value=True,
        )
        mock_delete = mocker.patch(
            "opticamanager.ui.views.usuarios_view.delete_user",
            return_value=None,
        )
        view._eliminar_usuario()
        mock_delete.assert_called_once_with(2)

    def test_error_al_eliminar_muestra_error(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        _fake_user_session(mocker, user_id=1)
        users = [_make_user_for_table(user_id=2)]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        mock_user = MagicMock()
        mock_user.id = 2
        mock_user.username = "user2"
        mock_user.active = True
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.get_user",
            return_value=mock_user,
        )
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.dialogo_confirmacion",
            return_value=True,
        )
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.delete_user",
            return_value="Error al eliminar",
        )
        mock_error = mocker.patch(
            "opticamanager.ui.views.usuarios_view.dialogo_error",
        )
        view._eliminar_usuario()
        mock_error.assert_called_once()

    def test_user_no_encontrado(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_user_session(mocker, user_id=1)
        users = [_make_user_for_table(user_id=2)]
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.list_users",
            return_value=users,
        )
        view = UsuariosView()
        qtbot.addWidget(view)
        view._tabla.view().selectRow(0)
        mocker.patch(
            "opticamanager.ui.views.usuarios_view.get_user",
            return_value=None,
        )
        view._eliminar_usuario()
        # Should return without crash


# ── UsuariosView Static Helper Tests ─────────────────────────────────────


class TestUsuariosViewHelpers:
    """Tests for static helper methods."""

    def test_get_selected_id(self) -> None:
        model = MagicMock()
        item = MagicMock()
        item.text.return_value = "42"
        model.item.return_value = item
        assert UsuariosView._get_selected_id(model, 0) == 42

    def test_get_selected_id_item_none(self) -> None:
        model = MagicMock()
        model.item.return_value = None
        assert UsuariosView._get_selected_id(model, 0) == 0
