from __future__ import annotations

import re

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from opticamanager.core.session import UserSession


class RegisterWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OpticaManager - Registrar Administrador")
        self.setFixedSize(400, 470)

        self._username_input = QLineEdit()
        self._username_input.setPlaceholderText("Usuario")

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Nombre completo")

        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("Correo electrónico")

        self._password_input = QLineEdit()
        self._password_input.setPlaceholderText("Contraseña (mín. 8 caracteres)")
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self._confirm_input = QLineEdit()
        self._confirm_input.setPlaceholderText("Confirmar contraseña")
        self._confirm_input.setEchoMode(QLineEdit.EchoMode.Password)

        self._register_btn = QPushButton("Registrar")
        self._register_btn.clicked.connect(self._on_register)

        self._username_input.returnPressed.connect(self._name_input.setFocus)
        self._name_input.returnPressed.connect(self._email_input.setFocus)
        self._email_input.returnPressed.connect(self._password_input.setFocus)
        self._password_input.returnPressed.connect(self._confirm_input.setFocus)
        self._confirm_input.returnPressed.connect(self._register_btn.click)

        self._demo_checkbox = QCheckBox("Cargar datos de demostración")
        self._demo_checkbox.setToolTip(
            "Crea productos (13), clientes (5), recetas (2) y ventas (6) de ejemplo.\n"
            'También crea un usuario "vendedor/vende123" de prueba.'
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(30, 20, 30, 20)
        layout.setSpacing(10)
        layout.addStretch()
        layout.addWidget(
            QLabel("Registrar Administrador"),
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        layout.addSpacing(5)
        layout.addWidget(
            QLabel("Crea la primera cuenta de administrador del sistema"),
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        layout.addSpacing(15)
        layout.addWidget(QLabel("Usuario:"))
        layout.addWidget(self._username_input)
        layout.addSpacing(5)
        layout.addWidget(QLabel("Nombre:"))
        layout.addWidget(self._name_input)
        layout.addSpacing(5)
        layout.addWidget(QLabel("Correo electrónico:"))
        layout.addWidget(self._email_input)
        layout.addSpacing(5)
        layout.addWidget(QLabel("Contraseña:"))
        layout.addWidget(self._password_input)
        layout.addSpacing(5)
        layout.addWidget(QLabel("Confirmar contraseña:"))
        layout.addWidget(self._confirm_input)
        layout.addSpacing(8)
        layout.addWidget(self._demo_checkbox)
        layout.addSpacing(10)
        layout.addWidget(self._register_btn)
        layout.addStretch()
        self.setLayout(layout)

    # ── Validation ──

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))

    def _on_register(self) -> None:
        username = self._username_input.text().strip()
        name = self._name_input.text().strip()
        email = self._email_input.text().strip()
        password = self._password_input.text()
        confirm = self._confirm_input.text()

        # ── Validate fields ──
        if not username or not name or not email or not password or not confirm:
            QMessageBox.warning(self, "Campos requeridos", "Completa todos los campos")
            return

        if len(username) < 3:
            QMessageBox.warning(
                self,
                "Usuario inválido",
                "El usuario debe tener al menos 3 caracteres",
            )
            return

        if len(name) < 2:
            QMessageBox.warning(
                self,
                "Nombre inválido",
                "El nombre debe tener al menos 2 caracteres",
            )
            return

        if not self._is_valid_email(email):
            QMessageBox.warning(
                self,
                "Correo inválido",
                "Ingresa un correo electrónico válido",
            )
            return

        if len(password) < 8:
            QMessageBox.warning(
                self,
                "Contraseña débil",
                "La contraseña debe tener al menos 8 caracteres",
            )
            return

        if password != confirm:
            QMessageBox.warning(
                self,
                "Contraseñas no coinciden",
                "Las contraseñas ingresadas no coinciden",
            )
            return

        # ── Register ──
        error = UserSession.register_admin(username, name, email, password)
        if error:
            QMessageBox.warning(self, "Error al registrar", error)
            return

        # ── Optional demo data ──
        if self._demo_checkbox.isChecked():
            from scripts.seed_demo import seed_demo_data  # noqa: PLC0415

            try:
                seed_demo_data(skip_users=True)
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Error al cargar demo",
                    f"El administrador se registró, pero ocurrió un error\n"
                    f"al cargar los datos de demostración:\n{exc}",
                )
                return
            else:
                QMessageBox.information(
                    self,
                    "Registro exitoso",
                    f"Administrador '{username}' registrado correctamente.\n\n"
                    "Datos de demostración cargados:\n"
                    "  • 13 productos con categorías\n"
                    "  • 5 clientes\n"
                    "  • 2 recetas ópticas\n"
                    "  • 6 ventas de ejemplo\n\n"
                    "Puedes iniciar sesión como:\n"
                    "  • admin (la cuenta que creaste)\n"
                    "  • vendedor / vende123",
                )
                self._go_to_login()
                return

        QMessageBox.information(
            self,
            "Registro exitoso",
            f"Administrador '{username}' registrado correctamente.\n\n"
            "Ahora puedes iniciar sesión con tus credenciales.",
        )
        self._go_to_login()

    def _go_to_login(self) -> None:
        from opticamanager.ui.login_window import LoginWindow  # noqa: PLC0415

        self._login_window = LoginWindow()
        self._login_window.show()
        self.close()
