"""Tests for ExchangeRateWidget: currency rate, refresh, manual mode."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox
from pytest_mock import MockerFixture

from opticamanager.services.exchange_rate import RateInfo
from opticamanager.ui.widgets.exchange_rate_widget import ExchangeRateWidget

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _make_rate_info(
    rate: Decimal = Decimal("36.50"),
    source: str = "bcv",
    updated_at: datetime | None = None,
) -> RateInfo:
    return RateInfo(rate=rate, source=source, updated_at=updated_at)


class TestCreacionWidget:
    """Smoke tests: the widget builds without error and has its full UI."""

    def test_creacion_basica(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        assert isinstance(w, ExchangeRateWidget)

    def test_placeholder_initial_state(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        assert "—" in w._rate_label.text()
        assert "Actualizar" in w._source_label.text()

    def test_botones_existentes(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        assert w._btn_refresh.text() == "Actualizar"
        assert w._btn_manual.text() == "Manual"
        assert w._btn_save_manual.text() == "Guardar"
        assert w._btn_cancel_manual.text() == "Cancelar"

    def test_manual_area_hidden_by_default(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        assert not w._manual_area.isVisible()


class TestShowEvent:
    """Tests for showEvent auto-fetch behavior."""

    def test_first_show_triggers_on_refresh(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        mock_refresh = mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.force_refresh"
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        # Reset after init to avoid counting the auto-fetch from _has_shown
        w._has_shown = False
        mock_refresh.reset_mock()
        from PyQt6.QtGui import QShowEvent

        w.showEvent(QShowEvent())
        mock_refresh.assert_called_once()

    def test_second_show_does_not_refresh(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        mock_refresh = mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.force_refresh"
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        w._has_shown = True
        mock_refresh.reset_mock()
        from PyQt6.QtGui import QShowEvent

        w.showEvent(QShowEvent())
        mock_refresh.assert_not_called()


class TestUpdateDisplay:
    """Tests for _update_display updating labels from get_rate_info."""

    def test_display_with_valid_rate(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        # Now mock for the actual _update_display call
        info = _make_rate_info(
            rate=Decimal("36.5000"),
            source="bcv",
            updated_at=datetime(2026, 9, 20, 10, 30),
        )
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=info,
        )
        w._update_display()
        assert "36.5000" in w._rate_label.text()
        assert "BCV" in w._source_label.text()

    def test_display_with_no_rate(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        info = _make_rate_info(rate=Decimal("0"), source="unknown")
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=info,
        )
        w._update_display()
        assert "no disponible" in w._rate_label.text()
        assert "—" in w._source_label.text()

    def test_display_with_manual_source(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        info = _make_rate_info(rate=Decimal("42.00"), source="manual")
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=info,
        )
        w._update_display()
        assert "Manual" in w._source_label.text()

    def test_display_with_timestamp(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        info = _make_rate_info(
            rate=Decimal("36.50"),
            source="bcv",
            updated_at=datetime(2026, 9, 20, 10, 30),
        )
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=info,
        )
        w._update_display()
        assert "20/09/2026" in w._time_label.text()

    def test_display_without_timestamp(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        info = _make_rate_info(rate=Decimal("36.50"), source="bcv", updated_at=None)
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=info,
        )
        w._update_display()
        assert w._time_label.text() == ""

    def test_emite_senial_cuando_rate_valido(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        info = _make_rate_info(rate=Decimal("36.50"))
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=info,
        )
        received: list[Decimal] = []
        w.rate_changed.connect(lambda rate: received.append(rate))
        w._update_display()
        assert received == [Decimal("36.50")]

    def test_no_emite_senial_cuando_rate_cero(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        info = _make_rate_info(rate=Decimal("0"))
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=info,
        )
        received: list[Decimal] = []
        w.rate_changed.connect(lambda rate: received.append(rate))
        w._update_display()
        assert received == []


class TestOnRefresh:
    """Tests for the refresh action."""

    def test_on_refresh_llama_servicios(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        mock_clear = mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.clear_manual_rate"
        )
        mock_force = mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.force_refresh"
        )
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("36.50")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        w._on_refresh()
        mock_clear.assert_called_once()
        mock_force.assert_called_once()

    def test_boton_actualizar_conecta_a_on_refresh(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        mock_refresh = mocker.patch.object(ExchangeRateWidget, "_on_refresh")
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        mock_refresh.reset_mock()
        qtbot.mouseClick(w._btn_refresh, Qt.MouseButton.LeftButton)
        mock_refresh.assert_called_once()

    def test_refresh_public_method(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        mock_on = mocker.patch.object(ExchangeRateWidget, "_on_refresh")
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        w.refresh()
        mock_on.assert_called_once()


class TestToggleManual:
    """Tests for toggling the manual rate input area."""

    def test_toggle_manual_muestra_area(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        assert w._manual_mode is False
        w._toggle_manual()
        assert w._manual_mode is True

    def test_toggle_manual_oculta_area(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        w._toggle_manual()  # show
        assert w._manual_mode is True
        w._toggle_manual()  # hide
        assert w._manual_mode is False

    def test_toggle_manual_prefill_current_rate(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        info = _make_rate_info(rate=Decimal("42.00"))
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=info,
        )
        w._toggle_manual()
        assert w._manual_spin.value() == 42.00

    def test_toggle_manual_sin_rate_no_prefill(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        info = _make_rate_info(rate=Decimal("0"))
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=info,
        )
        initial_val = w._manual_spin.value()
        w._toggle_manual()
        # No prefill when rate is 0; spinbox keeps previous value
        assert w._manual_spin.value() == initial_val

    def test_boton_manual_conecta_a_toggle(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        mock_toggle = mocker.patch.object(ExchangeRateWidget, "_toggle_manual")
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        mock_toggle.reset_mock()
        qtbot.mouseClick(w._btn_manual, Qt.MouseButton.LeftButton)
        mock_toggle.assert_called_once()

    def test_toggle_off_llama_update_display(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        w._manual_mode = True
        mock_update = mocker.patch.object(w, "_update_display")
        w._toggle_manual()
        mock_update.assert_called_once()


class TestSaveManualRate:
    """Tests for saving a manual rate."""

    def test_save_manual_rate_exitoso(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        mock_set = mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.set_manual_rate"
        )
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("50.00"), source="manual"),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        w._manual_spin.setValue(50.00)
        w._save_manual_rate()
        mock_set.assert_called_once_with(Decimal("50.00"))
        assert w._manual_mode is False

    def test_save_manual_rate_cero_muestra_warning(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        """Note: the spinbox has min=0.01, so value<=0 is unreachable through
        the normal UI. Mock value() to cover the branch."""
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        warned: list[str] = []
        mocker.patch.object(
            QMessageBox, "warning", side_effect=lambda *_a, **_k: warned.append("ok")
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        mocker.patch.object(w._manual_spin, "value", return_value=0.0)
        w._save_manual_rate()
        assert warned

    def test_boton_guardar_conecta_a_save(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        mock_save = mocker.patch.object(ExchangeRateWidget, "_save_manual_rate")
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        mock_save.reset_mock()
        qtbot.mouseClick(w._btn_save_manual, Qt.MouseButton.LeftButton)
        mock_save.assert_called_once()


class TestCancelManual:
    """Tests for canceling manual rate input."""

    def test_cancel_manual_oculta_area(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        w._manual_mode = True
        w._cancel_manual()
        assert w._manual_mode is False

    def test_boton_cancelar_conecta_a_cancel(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.ui.widgets.exchange_rate_widget.get_rate_info",
            return_value=_make_rate_info(rate=Decimal("0")),
        )
        mock_cancel = mocker.patch.object(ExchangeRateWidget, "_cancel_manual")
        w = ExchangeRateWidget()
        qtbot.addWidget(w)
        mock_cancel.reset_mock()
        qtbot.mouseClick(w._btn_cancel_manual, Qt.MouseButton.LeftButton)
        mock_cancel.assert_called_once()
