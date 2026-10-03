from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from opticamanager.core.session import UserSession

# Max failed attempts before a timed lockout
_MAX_LOGIN_ATTEMPTS: int = 5
_LOCKOUT_MINUTES: int = 1


class LoginWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OpticaManager - Iniciar Sesión")
        self.setFixedSize(360, 340)

        # ── Branding ──
        title_lbl = QLabel("OpticaManager")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setObjectName("login-title")

        subtitle_lbl = QLabel("Sistema de Gestión Óptica")
        subtitle_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_lbl.setObjectName("login-subtitle")

        # Separator line
        sep = QLabel()
        sep.setFixedHeight(2)
        sep.setObjectName("login-separator")

        # ── Form fields ──
        self._username_input = QLineEdit()
        self._username_input.setPlaceholderText("Usuario")

        self._password_input = QLineEdit()
        self._password_input.setPlaceholderText("Contraseña")
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self._login_btn = QPushButton("Ingresar")
        self._login_btn.clicked.connect(self._on_login)

        self._username_input.returnPressed.connect(self._password_input.setFocus)
        self._password_input.returnPressed.connect(self._login_btn.click)

        layout = QVBoxLayout()
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(6)
        layout.addStretch()
        layout.addWidget(title_lbl)
        layout.addSpacing(2)
        layout.addWidget(subtitle_lbl)
        layout.addSpacing(8)
        layout.addWidget(sep, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(12)
        layout.addWidget(
            QLabel("Iniciar Sesión"), alignment=Qt.AlignmentFlag.AlignCenter
        )
        layout.addSpacing(10)
        layout.addWidget(QLabel("Usuario:"))
        layout.addWidget(self._username_input)
        layout.addSpacing(4)
        layout.addWidget(QLabel("Contraseña:"))
        layout.addWidget(self._password_input)
        layout.addSpacing(12)
        layout.addWidget(self._login_btn)
        layout.addStretch()
        self.setLayout(layout)

        # ── Rate limiting state ──
        self._failed_attempts: int = 0
        self._locked_until: datetime | None = None

    def _is_locked(self) -> bool:
        """Check if the login is currently rate-limited."""
        if self._locked_until is None:
            return False
        if datetime.now(timezone.utc) >= self._locked_until:
            self._locked_until = None
            self._failed_attempts = 0
            self._set_inputs_enabled(True)
            return False
        return True

    def _lock(self) -> None:
        """Lock the login form for LOCKOUT_MINUTES."""
        self._locked_until = datetime.now(timezone.utc) + timedelta(
            minutes=_LOCKOUT_MINUTES
        )
        self._set_inputs_enabled(False)
        QTimer.singleShot(int(_LOCKOUT_MINUTES * 60 * 1000), self._release_lock)
        QMessageBox.warning(
            self,
            "Demasiados intentos",
            f"Has excedido {_MAX_LOGIN_ATTEMPTS} intentos fallidos. "
            f"Intenta de nuevo en {_LOCKOUT_MINUTES} minuto(s).",
        )

    def _release_lock(self) -> None:
        """Re-enable the form after lockout expires."""
        if self._locked_until and datetime.now(timezone.utc) >= self._locked_until:
            self._locked_until = None
            self._failed_attempts = 0
            self._set_inputs_enabled(True)

    def _set_inputs_enabled(self, enabled: bool) -> None:
        """Enable or disable login form inputs."""
        self._username_input.setEnabled(enabled)
        self._password_input.setEnabled(enabled)
        self._login_btn.setEnabled(enabled)

    def _on_login(self) -> None:
        locked_until = self._locked_until
        if locked_until is not None and datetime.now(timezone.utc) < locked_until:
            remaining = int((locked_until - datetime.now(timezone.utc)).total_seconds())
            QMessageBox.warning(
                self,
                "Cuenta bloqueada",
                f"Demasiados intentos fallidos. Espera {remaining}s.",
            )
            return

        username = self._username_input.text().strip()
        password = self._password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "Campos requeridos", "Completa todos los campos")
            return

        if UserSession().login(username, password):
            self._failed_attempts = 0
            from opticamanager.ui.main_window import MainWindow  # noqa: PLC0415

            self._main = MainWindow()
            self._main.show()
            self.close()
        else:
            self._failed_attempts += 1
            QMessageBox.warning(
                self, "Credenciales inválidas", "Usuario o contraseña incorrectos"
            )
            self._password_input.clear()

            if self._failed_attempts >= _MAX_LOGIN_ATTEMPTS:
                self._lock()
