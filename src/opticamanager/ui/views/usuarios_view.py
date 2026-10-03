from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from opticamanager.core.logging_config import get_logger
from opticamanager.core.session import UserSession
from opticamanager.services.user_service import (
    change_password,
    create_user,
    delete_user,
    get_user,
    list_roles,
    list_users,
    update_user,
)
from opticamanager.ui.widgets.dialogs import dialogo_confirmacion, dialogo_error
from opticamanager.ui.widgets.table_widget import TablaPersonalizada

log = get_logger(__name__)

# ── Colors ──
_COLOR_ACTIVE = QColor("#27ae60")
_COLOR_INACTIVE = QColor("#e74c3c")


class _UserDialog(QDialog):
    """Create / Edit user dialog.

    In *edit* mode (user is not None), password fields are hidden
    (use the separate password change button instead).
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        user_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._user_id = user_id
        self._editing = user_id is not None
        self.setWindowTitle("Editar Usuario" if self._editing else "Nuevo Usuario")
        self.setMinimumWidth(420)
        self._setup_ui()
        if self._editing and user_id is not None:
            self._load_user(user_id)

    def _setup_ui(self) -> None:
        form = QFormLayout()

        self._username = QLineEdit()
        self._username.setMaxLength(50)
        form.addRow("Usuario:", self._username)

        self._name = QLineEdit()
        self._name.setMaxLength(100)
        form.addRow("Nombre:", self._name)

        self._email = QLineEdit()
        self._email.setMaxLength(100)
        form.addRow("Correo electrónico:", self._email)

        # Role combo
        self._role_combo = QComboBox()
        roles = list_roles()
        for r in roles:
            assert r.id is not None
            self._role_combo.addItem(r.name, r.id)
        form.addRow("Rol:", self._role_combo)

        # Password (only for create)
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setMaxLength(128)
        if not self._editing:
            self._password.setPlaceholderText("Mín. 8 caracteres")
            form.addRow("Contraseña:", self._password)

            self._confirm = QLineEdit()
            self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
            form.addRow("Confirmar:", self._confirm)
        else:
            self._password.setVisible(False)

        # Active toggle
        self._active_cb = QCheckBox("Activo")
        self._active_cb.setChecked(True)
        if self._editing:
            form.addRow("Estado:", self._active_cb)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _load_user(self, user_id: int) -> None:
        user = get_user(user_id)
        if not user:
            return
        self._username.setText(user.username)
        self._username.setEnabled(False)  # Cannot change username
        self._name.setText(user.name)
        self._email.setText(user.email)

        # Select current role
        for i in range(self._role_combo.count()):
            if self._role_combo.itemData(i) == user.role_id:
                self._role_combo.setCurrentIndex(i)
                break

        self._active_cb.setChecked(user.active)

    def _validate_and_accept(self) -> None:
        if not self._username.text().strip():
            QMessageBox.warning(self, "Validación", "El usuario es obligatorio")
            return
        if len(self._username.text().strip()) < 3:
            QMessageBox.warning(
                self, "Validación", "El usuario debe tener al menos 3 caracteres"
            )
            return
        if not self._name.text().strip():
            QMessageBox.warning(self, "Validación", "El nombre es obligatorio")
            return
        if not self._is_valid_email(self._email.text().strip()):
            QMessageBox.warning(
                self, "Validación", "Ingresa un correo electrónico válido"
            )
            return

        if not self._editing:
            pwd = self._password.text()
            if len(pwd) < 8:
                QMessageBox.warning(
                    self, "Validación", "La contraseña debe tener al menos 8 caracteres"
                )
                return
            if pwd != self._confirm.text():
                QMessageBox.warning(self, "Validación", "Las contraseñas no coinciden")
                return

        self.accept()

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        import re

        return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))

    def get_data(self) -> dict:
        data: dict = {
            "username": self._username.text().strip(),
            "name": self._name.text().strip(),
            "email": self._email.text().strip(),
            "role_id": self._role_combo.currentData(),
            "active": self._active_cb.isChecked(),
        }
        if not self._editing:
            data["password"] = self._password.text()
        return data


class _PasswordDialog(QDialog):
    """Dialog to change a user's password."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cambiar Contraseña")
        self.setMinimumWidth(350)
        self._setup_ui()

    def _setup_ui(self) -> None:
        form = QFormLayout()

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("Mín. 8 caracteres")
        form.addRow("Nueva contraseña:", self._password)

        self._confirm = QLineEdit()
        self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Confirmar:", self._confirm)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _validate_and_accept(self) -> None:
        pwd = self._password.text()
        if len(pwd) < 8:
            QMessageBox.warning(
                self, "Validación", "La contraseña debe tener al menos 8 caracteres"
            )
            return
        if pwd != self._confirm.text():
            QMessageBox.warning(self, "Validación", "Las contraseñas no coinciden")
            return
        self.accept()

    def get_password(self) -> str:
        return self._password.text()


# ────────────────────────────────────────────────────────────
#  Main View
# ────────────────────────────────────────────────────────────


class UsuariosView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._setup_ui()
        self._load_data()

    # ── Helpers ──

    @staticmethod
    def _get_selected_id(model, row: int) -> int:
        item = model.item(row, 0)
        return int(item.text()) if item else 0

    def _selected_row(self) -> int | None:
        row = self._tabla.view().currentIndex().row()
        if row < 0:
            QMessageBox.information(
                self, "Seleccionar", "Seleccione un usuario de la tabla"
            )
            return None
        return row

    def _selected_user_id(self) -> int | None:
        row = self._selected_row()
        if row is None:
            return None
        proxy = self._tabla.proxy()
        source_idx = proxy.mapToSource(proxy.index(row, 0))
        return self._get_selected_id(self._tabla.model(), source_idx.row())

    def _current_user_id(self) -> int | None:
        """Return the logged-in user's id, or None."""
        user = UserSession().current_user
        return user.id if user else None

    # ── UI Setup ──

    def _setup_ui(self) -> None:
        title = QLabel("Usuarios")
        title.setObjectName("title-h2")

        btn_nuevo = QPushButton("+ Nuevo Usuario")
        btn_nuevo.setProperty("success", True)
        btn_nuevo.clicked.connect(self._nuevo_usuario)

        self._btn_editar = QPushButton("Editar")
        self._btn_editar.clicked.connect(self._editar_usuario)

        self._btn_password = QPushButton("Cambiar Contraseña")
        self._btn_password.clicked.connect(self._cambiar_password)

        self._btn_toggle = QPushButton("Activar/Desactivar")
        self._btn_toggle.clicked.connect(self._toggle_activo)

        self._btn_eliminar = QPushButton("Eliminar")
        self._btn_eliminar.setProperty("danger", True)
        self._btn_eliminar.clicked.connect(self._eliminar_usuario)

        toolbar = QHBoxLayout()
        toolbar.addWidget(btn_nuevo)
        toolbar.addWidget(self._btn_editar)
        toolbar.addWidget(self._btn_password)
        toolbar.addWidget(self._btn_toggle)
        toolbar.addWidget(self._btn_eliminar)
        toolbar.addStretch()

        self._tabla = TablaPersonalizada()
        self._tabla.set_columns(
            ["ID", "Usuario", "Nombre", "Email", "Rol", "Activo", "Creado"]
        )
        self._tabla.view().setColumnHidden(0, True)

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.addWidget(title)
        layout.addLayout(toolbar)
        layout.addWidget(self._tabla)
        self.setLayout(layout)

    def _load_data(self) -> None:
        self._tabla.clear()
        users = list_users()
        for u in users:
            active_text = "Sí" if u.active else "No"
            created = u.created_at.strftime("%d/%m/%Y") if u.created_at else "—"
            role_name = u.role.name if u.role else "—"

            row = self._tabla.add_row(
                [
                    str(u.id),
                    u.username,
                    u.name,
                    u.email,
                    role_name,
                    active_text,
                    created,
                ]
            )

            # Color the "Activo" column
            color = _COLOR_ACTIVE if u.active else _COLOR_INACTIVE
            active_item = self._tabla.model().item(row, 5)
            if active_item:
                active_item.setForeground(color)
                active_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    # ── Actions ──

    def _nuevo_usuario(self) -> None:
        dlg = _UserDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        error = create_user(**data)
        if error:
            dialogo_error(self, "Error", "No se pudo crear el usuario", error)
            return
        self._load_data()

    def _editar_usuario(self) -> None:
        user_id = self._selected_user_id()
        if user_id is None:
            return
        dlg = _UserDialog(self, user_id)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        # Remove username/password from data (not editable / separate action)
        data.pop("username", None)
        data.pop("password", None)
        error = update_user(user_id, **data)
        if error:
            dialogo_error(self, "Error", "No se pudo editar el usuario", error)
            return
        self._load_data()

    def _cambiar_password(self) -> None:
        user_id = self._selected_user_id()
        if user_id is None:
            return
        dlg = _PasswordDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_password = dlg.get_password()
        error = change_password(user_id, new_password)
        if error:
            dialogo_error(self, "Error", "No se pudo cambiar la contraseña", error)
            return
        QMessageBox.information(
            self, "Contraseña", "Contraseña actualizada correctamente"
        )

    def _toggle_activo(self) -> None:
        user_id = self._selected_user_id()
        if user_id is None:
            return

        # Prevent deactivating self
        if user_id == self._current_user_id():
            QMessageBox.warning(
                self, "Acción no permitida", "No puedes desactivar tu propio usuario"
            )
            return

        user = get_user(user_id)
        if not user:
            return

        new_active = not user.active
        action = "activar" if new_active else "desactivar"

        if not dialogo_confirmacion(
            self,
            f"{'Activar' if new_active else 'Desactivar'} Usuario",
            f"¿{action.capitalize()} al usuario '{user.username}'?",
        ):
            return

        error = update_user(
            user_id,
            name=user.name,
            email=user.email,
            role_id=user.role_id,
            active=new_active,
        )
        if error:
            dialogo_error(self, "Error", f"No se pudo {action} el usuario", error)
            return
        self._load_data()

    def _eliminar_usuario(self) -> None:
        user_id = self._selected_user_id()
        if user_id is None:
            return

        # Prevent deleting self
        if user_id == self._current_user_id():
            QMessageBox.warning(
                self, "Acción no permitida", "No puedes eliminar tu propio usuario"
            )
            return

        user = get_user(user_id)
        if not user:
            return

        if not dialogo_confirmacion(
            self,
            "Eliminar Usuario",
            f"¿Eliminar al usuario '{user.username}'?\n\n"
            "Esta acción no se puede deshacer.",
        ):
            return

        error = delete_user(user_id)
        if error:
            dialogo_error(self, "Error", "No se pudo eliminar el usuario", error)
            return
        self._load_data()
