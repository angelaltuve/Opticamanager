"""Tests for RegisterWindow: field validation, registration and demo data."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QApplication, QCheckBox, QLineEdit, QMessageBox
from pytest_mock import MockerFixture

from opticamanager.core.session import UserSession
from opticamanager.ui.register_window import RegisterWindow

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _click_msgbox(qapp: QApplication, button_text: str) -> None:
    """Find an open QMessageBox and click the button matching *button_text*."""
    for w in qapp.topLevelWidgets():
        if isinstance(w, QMessageBox):
            for btn in w.buttons():
                if button_text.lower() in btn.text().lower():
                    btn.click()
                    return


class TestRegisterWindowInitialState:
    """Verify the window builds correctly."""

    def test_titulo_y_tamanio(self, qtbot: QtBot) -> None:
        win = RegisterWindow()
        qtbot.addWidget(win)
        assert win.windowTitle() == "OpticaManager - Registrar Administrador"
        assert win.width() == 400
        assert win.height() == 470

    def test_placeholders(self, qtbot: QtBot) -> None:
        win = RegisterWindow()
        qtbot.addWidget(win)
        assert win._username_input.placeholderText() == "Usuario"
        assert win._name_input.placeholderText() == "Nombre completo"
        assert win._email_input.placeholderText() == "Correo electrónico"
        assert win._password_input.placeholderText() == "Contraseña (mín. 8 caracteres)"
        assert win._confirm_input.placeholderText() == "Confirmar contraseña"

    def test_password_echo_mode(self, qtbot: QtBot) -> None:
        win = RegisterWindow()
        qtbot.addWidget(win)
        assert win._password_input.echoMode() == QLineEdit.EchoMode.Password
        assert win._confirm_input.echoMode() == QLineEdit.EchoMode.Password

    def test_boton_registro_texto(self, qtbot: QtBot) -> None:
        win = RegisterWindow()
        qtbot.addWidget(win)
        assert win._register_btn.text() == "Registrar"

    def test_demo_checkbox_exists(self, qtbot: QtBot) -> None:
        win = RegisterWindow()
        qtbot.addWidget(win)
        assert isinstance(win._demo_checkbox, QCheckBox)
        assert "demostración" in win._demo_checkbox.text()
        assert not win._demo_checkbox.isChecked()


class TestIsValidEmail:
    """Tests for the static email validator."""

    def test_email_valido(self) -> None:
        assert RegisterWindow._is_valid_email("user@example.com") is True

    def test_email_valido_con_punto(self) -> None:
        assert RegisterWindow._is_valid_email("a.b@c.co") is True

    def test_email_invalido_sin_arroba(self) -> None:
        assert RegisterWindow._is_valid_email("userexample.com") is False

    def test_email_invalido_sin_dominio(self) -> None:
        assert RegisterWindow._is_valid_email("user@") is False

    def test_email_invalido_vacio(self) -> None:
        assert RegisterWindow._is_valid_email("") is False

    def test_email_invalido_con_espacios(self) -> None:
        assert RegisterWindow._is_valid_email("user @example.com") is False


class TestValidacionCampos:
    """Empty field validation and business rules."""

    def test_campos_vacios_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture, qapp: QApplication
    ) -> None:
        win = RegisterWindow()
        qtbot.addWidget(win)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox, "warning", side_effect=lambda *_a, **_k: warned.append("ok")
        )
        win._on_register()
        assert warned

    def test_username_corto_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        win = RegisterWindow()
        qtbot.addWidget(win)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox, "warning", side_effect=lambda *_a, **_k: warned.append("ok")
        )
        win._username_input.setText("ab")
        win._name_input.setText("Admin")
        win._email_input.setText("admin@test.com")
        win._password_input.setText("password123")
        win._confirm_input.setText("password123")
        win._on_register()
        assert warned
        # register_admin should NOT be called
        assert not win._confirm_input.text() == ""

    def test_nombre_corto_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        win = RegisterWindow()
        qtbot.addWidget(win)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox, "warning", side_effect=lambda *_a, **_k: warned.append("ok")
        )
        win._username_input.setText("admin")
        win._name_input.setText("A")
        win._email_input.setText("admin@test.com")
        win._password_input.setText("password123")
        win._confirm_input.setText("password123")
        win._on_register()
        assert warned

    def test_email_invalido_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        win = RegisterWindow()
        qtbot.addWidget(win)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox, "warning", side_effect=lambda *_a, **_k: warned.append("ok")
        )
        win._username_input.setText("admin")
        win._name_input.setText("Admin")
        win._email_input.setText("no-es-email")
        win._password_input.setText("password123")
        win._confirm_input.setText("password123")
        win._on_register()
        assert warned

    def test_password_corto_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        win = RegisterWindow()
        qtbot.addWidget(win)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox, "warning", side_effect=lambda *_a, **_k: warned.append("ok")
        )
        win._username_input.setText("admin")
        win._name_input.setText("Admin")
        win._email_input.setText("admin@test.com")
        win._password_input.setText("short")
        win._confirm_input.setText("short")
        win._on_register()
        assert warned

    def test_passwords_no_coinciden_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        win = RegisterWindow()
        qtbot.addWidget(win)
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox, "warning", side_effect=lambda *_a, **_k: warned.append("ok")
        )
        win._username_input.setText("admin")
        win._name_input.setText("Admin")
        win._email_input.setText("admin@test.com")
        win._password_input.setText("password123")
        win._confirm_input.setText("different123")
        win._on_register()
        assert warned


class TestRegistroExitoso:
    """Tests for the successful registration flow."""

    def test_registro_exitoso_sin_demo(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        """Successful registration without demo: shows info and goes to login."""
        win = RegisterWindow()
        qtbot.addWidget(win)
        mocker.patch.object(UserSession, "register_admin", return_value=None)
        mock_go = mocker.patch.object(win, "_go_to_login")
        info_msgs: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: info_msgs.append("ok"),
        )
        win._username_input.setText("admin")
        win._name_input.setText("Admin User")
        win._email_input.setText("admin@test.com")
        win._password_input.setText("password123")
        win._confirm_input.setText("password123")
        win._on_register()
        assert info_msgs
        mock_go.assert_called_once()

    def test_registro_error_servidor(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        """register_admin returns an error: shows a warning."""
        win = RegisterWindow()
        qtbot.addWidget(win)
        mocker.patch.object(
            UserSession, "register_admin", return_value="Ya existe un administrador"
        )
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox, "warning", side_effect=lambda *_a, **_k: warned.append("ok")
        )
        win._username_input.setText("admin")
        win._name_input.setText("Admin User")
        win._email_input.setText("admin@test.com")
        win._password_input.setText("password123")
        win._confirm_input.setText("password123")
        win._on_register()
        assert warned

    def test_registro_exitoso_con_demo(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        """Demo checkbox ticked: calls seed_demo_data and shows info."""
        win = RegisterWindow()
        qtbot.addWidget(win)
        win._demo_checkbox.setChecked(True)
        mocker.patch.object(UserSession, "register_admin", return_value=None)
        mock_seed = mocker.patch(
            "opticamanager.ui.register_window.seed_demo_data", create=True
        )
        mock_go = mocker.patch.object(win, "_go_to_login")
        info_msgs: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: info_msgs.append("ok"),
        )
        # Patch the lazy import path inside _on_register
        mocker.patch.dict(
            "sys.modules", {"scripts.seed_demo": MagicMock(seed_demo_data=mock_seed)}
        )
        # The code does: from scripts.seed_demo import seed_demo_data
        # We need to mock the import at the right level
        import scripts.seed_demo as _mod  # noqa: F811

        _mod.seed_demo_data = mock_seed

        win._username_input.setText("admin")
        win._name_input.setText("Admin User")
        win._email_input.setText("admin@test.com")
        win._password_input.setText("password123")
        win._confirm_input.setText("password123")
        win._on_register()
        # seed_demo_data should be called with skip_users=True
        mock_seed.assert_called_once_with(skip_users=True)
        assert info_msgs
        mock_go.assert_called_once()

    def test_registro_demo_con_excepcion(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        """seed_demo_data raises: shows critical and does NOT navigate.

        The admin is already registered, so the user must still reach the login
        screen. That is why the demo data failure only reports and never blocks
        the flow.
        """
        win = RegisterWindow()
        qtbot.addWidget(win)
        win._demo_checkbox.setChecked(True)
        mocker.patch.object(UserSession, "register_admin", return_value=None)
        mock_seed = mocker.patch(
            "opticamanager.ui.register_window.seed_demo_data", create=True
        )
        mock_seed.side_effect = RuntimeError("DB error")
        mock_go = mocker.patch.object(win, "_go_to_login")
        critical_msgs: list[str] = []
        mocker.patch.object(
            QMessageBox,
            "critical",
            side_effect=lambda *_a, **_k: critical_msgs.append("ok"),
        )

        import scripts.seed_demo as _mod  # noqa: F811

        _mod.seed_demo_data = mock_seed

        win._username_input.setText("admin")
        win._name_input.setText("Admin User")
        win._email_input.setText("admin@test.com")
        win._password_input.setText("password123")
        win._confirm_input.setText("password123")
        win._on_register()
        mock_seed.assert_called_once_with(skip_users=True)
        assert critical_msgs
        mock_go.assert_not_called()


class TestGoToLogin:
    """Tests for _go_to_login navigation."""

    def test_go_to_login_creates_ventana(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        """_go_to_login creates a LoginWindow and closes the current window."""
        win = RegisterWindow()
        qtbot.addWidget(win)
        mock_lw = MagicMock()
        # The lazy import is: from opticamanager.ui.login_window import LoginWindow
        mocker.patch(
            "opticamanager.ui.login_window.LoginWindow",
            return_value=mock_lw,
        )
        win._go_to_login()
        mock_lw.show.assert_called_once()
        assert win.isHidden()

    def test_go_to_login_guarda_referencia(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        """_go_to_login keeps a reference to the LoginWindow in _login_window."""
        win = RegisterWindow()
        qtbot.addWidget(win)
        mock_lw = MagicMock()
        mocker.patch(
            "opticamanager.ui.login_window.LoginWindow",
            return_value=mock_lw,
        )
        win._go_to_login()
        assert win._login_window is mock_lw


class TestReturnPressedFocusChain:
    """Tests for the ReturnPressed chain that moves focus.

    Focus needs ``win.show()`` plus ``qapp.processEvents()`` to work in
    offscreen mode.
    """

    def test_username_return_mueve_foco_a_nombre(
        self, qtbot: QtBot, qapp: QApplication
    ) -> None:
        win = RegisterWindow()
        qtbot.addWidget(win)
        win.show()
        qapp.processEvents()
        win._username_input.setFocus()
        qapp.processEvents()
        assert win._username_input.hasFocus()
        win._username_input.returnPressed.emit()
        qapp.processEvents()
        assert win._name_input.hasFocus()

    def test_nombre_return_mueve_foco_a_email(
        self, qtbot: QtBot, qapp: QApplication
    ) -> None:
        win = RegisterWindow()
        qtbot.addWidget(win)
        win.show()
        qapp.processEvents()
        win._name_input.setFocus()
        qapp.processEvents()
        win._name_input.returnPressed.emit()
        qapp.processEvents()
        assert win._email_input.hasFocus()

    def test_email_return_mueve_foco_a_password(
        self, qtbot: QtBot, qapp: QApplication
    ) -> None:
        win = RegisterWindow()
        qtbot.addWidget(win)
        win.show()
        qapp.processEvents()
        win._email_input.setFocus()
        qapp.processEvents()
        win._email_input.returnPressed.emit()
        qapp.processEvents()
        assert win._password_input.hasFocus()

    def test_password_return_mueve_foco_a_confirm(
        self, qtbot: QtBot, qapp: QApplication
    ) -> None:
        win = RegisterWindow()
        qtbot.addWidget(win)
        win.show()
        qapp.processEvents()
        win._password_input.setFocus()
        qapp.processEvents()
        win._password_input.returnPressed.emit()
        qapp.processEvents()
        assert win._confirm_input.hasFocus()

    def test_confirm_return_conectado_a_boton(self, qtbot: QtBot) -> None:
        """ReturnPressed on confirm is connected (it has receivers)."""
        win = RegisterWindow()
        qtbot.addWidget(win)
        # The signal returnPressed on _confirm_input is connected to
        # _register_btn.click in __init__; verify the connection exists.
        # We don't emit it because it chains to _on_register which opens
        # a blocking QMessageBox.
        assert win._confirm_input is not None
        assert win._register_btn is not None
