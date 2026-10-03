"""Widget to display and manage the BCV exchange rate."""

from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from opticamanager.core.logging_config import get_logger
from opticamanager.services.exchange_rate import (
    RateInfo,
    clear_manual_rate,
    force_refresh,
    get_rate_info,
    set_manual_rate,
)

log = get_logger(__name__)


class ExchangeRateWidget(QFrame):
    """Compact widget displaying the current USD/BCV exchange rate.

    Shows the rate fetched from BCV or a manually entered value.
    Provides buttons to refresh or manually override the rate.
    """

    rate_changed = pyqtSignal(Decimal)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manual_mode: bool = False
        self._has_shown: bool = False
        self._setup_ui()
        self._show_placeholder()

    def showEvent(self, a0) -> None:  # noqa: N802
        """Auto-fetch rate the first time the widget becomes visible."""
        super().showEvent(a0)
        if not self._has_shown:
            self._has_shown = True
            self._on_refresh()

    def _show_placeholder(self) -> None:
        """Show initial placeholder state; no fetch yet."""
        self._rate_label.setText("1 USD = — Bs")
        self._source_label.setText("Presione 'Actualizar'")
        self._source_label.setProperty("source", "unknown")
        self._source_label.style().unpolish(self._source_label)
        self._source_label.style().polish(self._source_label)
        self._time_label.setText("")

    def _setup_ui(self) -> None:
        self.setFrameStyle(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # ── Header row ──
        header = QLabel("Tasa Cambiaria BCV")
        header.setObjectName("title-h3")
        layout.addWidget(header)

        # ── Rate display ──
        self._rate_label = QLabel("1 USD = — Bs")
        self._rate_label.setObjectName("title-h3")
        layout.addWidget(self._rate_label)

        # ── Metadata row ──
        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)

        self._source_label = QLabel("")
        self._source_label.setObjectName("rate-source")
        meta_row.addWidget(self._source_label)

        self._time_label = QLabel("")
        self._time_label.setObjectName("muted")
        meta_row.addWidget(self._time_label)

        meta_row.addStretch()
        layout.addLayout(meta_row)

        # ── Action buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._btn_refresh = QPushButton("Actualizar")
        self._btn_refresh.setFixedHeight(28)
        self._btn_refresh.clicked.connect(self._on_refresh)
        btn_row.addWidget(self._btn_refresh)

        self._btn_manual = QPushButton("Manual")
        self._btn_manual.setFixedHeight(28)
        self._btn_manual.clicked.connect(self._toggle_manual)
        btn_row.addWidget(self._btn_manual)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── Manual input area (hidden by default) ──
        self._manual_area = QWidget()
        manual_layout = QHBoxLayout(self._manual_area)
        manual_layout.setContentsMargins(0, 4, 0, 0)
        manual_layout.setSpacing(6)

        manual_layout.addWidget(QLabel("Tasa manual:"))

        self._manual_spin = QDoubleSpinBox()
        self._manual_spin.setRange(0.01, 9_999_999.99)
        self._manual_spin.setDecimals(4)
        self._manual_spin.setPrefix("Bs. ")
        self._manual_spin.setValue(0)
        self._manual_spin.setFixedWidth(140)
        manual_layout.addWidget(self._manual_spin)

        self._btn_save_manual = QPushButton("Guardar")
        self._btn_save_manual.setFixedHeight(26)
        self._btn_save_manual.clicked.connect(self._save_manual_rate)
        manual_layout.addWidget(self._btn_save_manual)

        self._btn_cancel_manual = QPushButton("Cancelar")
        self._btn_cancel_manual.setFixedHeight(26)
        self._btn_cancel_manual.clicked.connect(self._cancel_manual)
        manual_layout.addWidget(self._btn_cancel_manual)

        manual_layout.addStretch()
        self._manual_area.setVisible(False)
        layout.addWidget(self._manual_area)

        self.setLayout(layout)

    def _update_display(self) -> None:
        """Refresh the displayed rate and metadata from the service."""
        info: RateInfo = get_rate_info()

        if info.rate and info.rate > 0:
            self._rate_label.setText(f"1 USD = {info.rate:,.4f} Bs")
        else:
            self._rate_label.setText("1 USD = — Bs (no disponible)")

        # Source indicator
        if info.source == "bcv":
            self._source_label.setText("Fuente: BCV")
            self._source_label.setProperty("source", "bcv")
        elif info.source == "manual":
            self._source_label.setText("Fuente: Manual")
            self._source_label.setProperty("source", "manual")
        else:
            self._source_label.setText("Fuente: —")
            self._source_label.setProperty("source", "unknown")
        self._source_label.style().unpolish(self._source_label)
        self._source_label.style().polish(self._source_label)

        # Timestamp
        if info.updated_at:
            self._time_label.setText(f"📅 {info.updated_at.strftime('%d/%m/%Y %H:%M')}")
        else:
            self._time_label.setText("")

        # Emit signal if we have a valid rate
        if info.rate and info.rate > 0:
            self.rate_changed.emit(info.rate)

    # ── Actions ─────────────────────────────────

    def _on_refresh(self) -> None:
        """Force-refresh the rate from BCV, clearing any manual override."""
        clear_manual_rate()
        self._cancel_manual()
        force_refresh()
        self._update_display()

    def _toggle_manual(self) -> None:
        """Show or hide the manual rate input area."""
        self._manual_mode = not self._manual_mode
        self._manual_area.setVisible(self._manual_mode)

        if self._manual_mode:
            # Pre-fill with current rate if available
            info = get_rate_info()
            if info.rate and info.rate > 0:
                self._manual_spin.setValue(float(info.rate))
            self._manual_spin.setFocus()
        else:
            self._update_display()

    def _save_manual_rate(self) -> None:
        """Save the manually entered rate."""
        value = self._manual_spin.value()
        if value <= 0:
            QMessageBox.warning(
                self,
                "Tasa inválida",
                "Ingrese un valor mayor a cero para la tasa manual.",
            )
            return

        rate = Decimal(str(value))
        set_manual_rate(rate)
        log.info("Manual rate set via widget: 1 USD = %s Bs", rate)
        self._manual_mode = False
        self._manual_area.setVisible(False)
        self._update_display()

    def _cancel_manual(self) -> None:
        """Close manual input area without saving."""
        self._manual_mode = False
        self._manual_area.setVisible(False)

    def refresh(self) -> None:
        """Public method to trigger a refresh from outside."""
        self._on_refresh()
