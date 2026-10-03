"""Settings view: IVA rate configuration (Admin only)."""

from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from opticamanager.core.logging_config import get_logger
from opticamanager.core.session import UserSession
from opticamanager.services.settings_service import get_iva_rate, set_iva_rate
from opticamanager.ui.widgets.dialogs import dialogo_error

log = get_logger(__name__)


class SettingsView(QWidget):
    """Global application settings panel.

    Only users with role 'admin' (case-insensitive) may edit values.
    """

    def __init__(self) -> None:
        super().__init__()
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        self.setObjectName("settings-view")
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)

        # ── Header ──
        title = QLabel("Ajustes")
        title.setObjectName("title-h1")
        layout.addWidget(title)

        description = QLabel("Configuración global del sistema")
        description.setObjectName("subtitle")
        description.setStyleSheet("color: #7f8c8d; margin-bottom: 6px;")
        layout.addWidget(description)

        # ── Card ──
        card = QFrame()
        card.setObjectName("settings-card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        card_title = QLabel("Impuesto IVA")
        card_title.setObjectName("section-title")
        card_layout.addWidget(card_title)

        card_desc = QLabel(
            "Define el porcentaje de IVA aplicado a las ventas en el POS."
        )
        card_desc.setWordWrap(True)
        card_desc.setStyleSheet("color: #7f8c8d;")
        card_layout.addWidget(card_desc)

        # ── IVA form ──
        form = QFormLayout()
        form.setSpacing(8)

        self._iva_spin = QDoubleSpinBox()
        self._iva_spin.setRange(0, 100)
        self._iva_spin.setDecimals(2)
        self._iva_spin.setSuffix(" %")
        self._iva_spin.setValue(16)
        self._iva_spin.valueChanged.connect(self._on_iva_changed)
        form.addRow("Tasa de IVA:", self._iva_spin)

        card_layout.addLayout(form)
        card_layout.addStretch()

        # ── Save button (initially hidden) ──
        self._save_container = QWidget()
        save_layout = QHBoxLayout(self._save_container)
        save_layout.setContentsMargins(0, 0, 0, 0)

        self._save_btn = QPushButton("Guardar cambios")
        self._save_btn.setObjectName("btn-save")
        self._save_btn.clicked.connect(self._on_save)
        save_layout.addWidget(self._save_btn)
        save_layout.addStretch()

        self._save_container.setVisible(False)
        card_layout.addWidget(self._save_container)

        layout.addWidget(card)
        layout.addStretch()

        self.setLayout(layout)

        # ── Admin gate ──
        user = UserSession().current_user
        if user and user.role_name.lower() == "admin":
            self._can_edit = True
        else:
            self._can_edit = False
            self._iva_spin.setEnabled(False)
            info = QLabel(
                "Solo los usuarios con rol Administrador pueden modificar "
                "la configuración."
            )
            info.setObjectName("info-admin")
            info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            info.setStyleSheet("color: #95a5a6; font-style: italic; padding: 8px;")
            layout.insertWidget(2, info)

    def _load_settings(self) -> None:
        """Read current IVA rate from DB and update spin."""
        rate = get_iva_rate()
        # Assign originals BEFORE setValue() so the valueChanged->_on_iva_changed
        # handler (already connected in _setup_ui) can read _original_iva instead
        # of raising AttributeError on the synchronous setValue() emit.
        self._original_iva = rate
        self._dirty = False
        self._iva_spin.setValue(float(rate * 100))

    def _on_iva_changed(self, value: float) -> None:
        """Track whether the value has changed from original."""
        new_rate = Decimal(str(value)) / Decimal("100")
        dirty = new_rate != self._original_iva
        self._dirty = dirty
        self._save_container.setVisible(dirty)

    def _on_save(self) -> None:
        """Persist the new IVA rate."""
        if not self._can_edit:
            return
        rate = Decimal(str(self._iva_spin.value())) / Decimal("100")
        try:
            set_iva_rate(rate)
        except ValueError as exc:
            log.warning("Rejected IVA rate %s: %s", rate, exc)
            dialogo_error(self, "IVA inválido", str(exc))
            return
        self._original_iva = rate
        self._dirty = False
        self._save_container.setVisible(False)
        log.info("IVA rate updated to %.2f%%", float(rate * 100))
        QMessageBox.information(
            self,
            "IVA actualizado",
            f"La tasa de IVA se ha actualizado a {float(rate * 100):.2f}%.",
        )
