from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox
from pytest_mock import MockerFixture

from opticamanager.core.session import UserSession
from opticamanager.ui.login_window import (
    LoginWindow,
    _LOCKOUT_MINUTES,
    _MAX_LOGIN_ATTEMPTS,
)

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


class TestLoginWindow:
    def test_login_window_initial_state(self, qtbot: QtBot) -> None:
        window = LoginWindow()
        qtbot.addWidget(window)

        assert window.windowTitle() == "OpticaManager - Iniciar Sesión"
        assert window.width() == 360
        assert window.height() == 340

        assert window._username_input.placeholderText() == "Usuario"
        assert window._password_input.placeholderText() == "Contraseña"
        assert (
            window._password_input.echoMode()
            == window._password_input.EchoMode.Password
        )
        assert window._login_btn.text() == "Ingresar"

    def test_empty_username_shows_warning(
        self, qtbot: QtBot, qapp: QApplication
    ) -> None:
        window = LoginWindow()
        qtbot.addWidget(window)

        window._username_input.setText("")
        window._password_input.setText("secret")

        QTimer.singleShot(200, lambda: _click_msgbox(qapp, "OK"))
        qtbot.mouseClick(window._login_btn, Qt.MouseButton.LeftButton)

    def test_empty_password_shows_warning(
        self, qtbot: QtBot, qapp: QApplication
    ) -> None:
        window = LoginWindow()
        qtbot.addWidget(window)

        window._username_input.setText("admin")
        window._password_input.setText("")

        QTimer.singleShot(200, lambda: _click_msgbox(qapp, "OK"))
        qtbot.mouseClick(window._login_btn, Qt.MouseButton.LeftButton)

    def test_successful_login(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mock_login = mocker.patch.object(UserSession, "login", return_value=True)
        mocker.patch("opticamanager.ui.main_window.MainWindow")

        window = LoginWindow()
        qtbot.addWidget(window)

        window._username_input.setText("admin")
        window._password_input.setText("secret")

        qtbot.mouseClick(window._login_btn, Qt.MouseButton.LeftButton)

        assert mock_login.call_count == 1
        mock_login.assert_called_with("admin", "secret")
        assert window.isHidden() or not window.isVisible()

    def test_failed_login_shows_warning(
        self, qtbot: QtBot, mocker: MockerFixture, qapp: QApplication
    ) -> None:
        mock_login = mocker.patch.object(UserSession, "login", return_value=False)
        mocker.patch("opticamanager.ui.main_window.MainWindow")

        window = LoginWindow()
        qtbot.addWidget(window)

        window._username_input.setText("admin")
        window._password_input.setText("wrong")

        QTimer.singleShot(200, lambda: _click_msgbox(qapp, "OK"))
        qtbot.mouseClick(window._login_btn, Qt.MouseButton.LeftButton)

        assert mock_login.call_count == 1
        mock_login.assert_called_with("admin", "wrong")
        assert window._password_input.text() == ""

    def test_enter_key_triggers_login(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mock_login = mocker.patch.object(UserSession, "login", return_value=True)
        mocker.patch("opticamanager.ui.main_window.MainWindow")

        window = LoginWindow()
        qtbot.addWidget(window)

        window._username_input.setText("admin")
        window._password_input.setText("secret")

        window._password_input.returnPressed.emit()

        assert mock_login.call_count == 1
        mock_login.assert_called_with("admin", "secret")


class TestLoginLockout:
    def test_cinco_intentos_fallidos_bloquean_el_formulario(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        warn = mocker.patch("opticamanager.ui.login_window.QMessageBox.warning")
        mocker.patch.object(UserSession, "login", return_value=False)
        mocker.patch("opticamanager.ui.login_window.QTimer.singleShot")

        window = LoginWindow()
        qtbot.addWidget(window)
        window._username_input.setText("admin")

        for _ in range(_MAX_LOGIN_ATTEMPTS):
            window._password_input.setText("wrong")  # clear() on each failure
            window._on_login()

        assert window._failed_attempts == _MAX_LOGIN_ATTEMPTS
        assert window._locked_until is not None
        assert not window._username_input.isEnabled()
        assert not window._password_input.isEnabled()
        assert not window._login_btn.isEnabled()

        # Lock warning was shown (title check)
        titles = [call.args[1] for call in warn.call_args_list]
        assert "Demasiados intentos" in titles

    def test_sexto_intento_bloqueado_no_llama_login(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mock_login = mocker.patch.object(UserSession, "login", return_value=False)
        warn = mocker.patch("opticamanager.ui.login_window.QMessageBox.warning")
        mocker.patch("opticamanager.ui.login_window.QTimer.singleShot")

        window = LoginWindow()
        qtbot.addWidget(window)
        window._username_input.setText("admin")
        window._password_input.setText("wrong")

        # Reach the lockout state
        for _ in range(_MAX_LOGIN_ATTEMPTS):
            window._password_input.setText("wrong")
            window._on_login()
        mock_login.reset_mock()

        # A further attempt while locked must not hit the login path
        window._on_login()
        mock_login.assert_not_called()

        titles = [call.args[1] for call in warn.call_args_list]
        assert "Cuenta bloqueada" in titles
        assert window._password_input.text() == ""

    def test_lock_expirado_libera_el_formulario(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch("opticamanager.ui.login_window.QMessageBox.warning")
        mocker.patch("opticamanager.ui.login_window.QTimer.singleShot")

        window = LoginWindow()
        qtbot.addWidget(window)

        # Simulate a lock whose window has already elapsed
        window._locked_until = datetime.now(timezone.utc) - timedelta(
            minutes=_LOCKOUT_MINUTES + 1
        )
        window._failed_attempts = _MAX_LOGIN_ATTEMPTS
        window._set_inputs_enabled(False)

        assert window._is_locked() is False
        assert window._locked_until is None
        assert window._failed_attempts == 0
        assert window._username_input.isEnabled()
        assert window._password_input.isEnabled()
        assert window._login_btn.isEnabled()

    def test_lock_activo_devuelve_true(self, qtbot: QtBot) -> None:
        window = LoginWindow()
        qtbot.addWidget(window)

        window._locked_until = datetime.now(timezone.utc) + timedelta(minutes=1)
        assert window._is_locked() is True
