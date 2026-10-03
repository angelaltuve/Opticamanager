"""Tests for SettingsView: global settings (IVA rate).

Coverage target: >=70% of ajustes_view.py
Strategy: mock settings_service and UserSession to stay off the real DB.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMessageBox
from pytest_mock import MockerFixture

from opticamanager.core.session import UserSession, UserData
from opticamanager.ui.views.ajustes_view import SettingsView

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


# ── Helpers ──────────────────────────────────────────────────────────────


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


# ── SettingsView Creation Tests ──────────────────────────────────────────


class TestSettingsViewCreacion:
    """Smoke tests for SettingsView creation."""

    def test_creacion_como_admin(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_user_session(mocker, role_name="Admin")
        mocker.patch(
            "opticamanager.ui.views.ajustes_view.get_iva_rate",
            return_value=Decimal("0.16"),
        )
        view = SettingsView()
        qtbot.addWidget(view)
        assert isinstance(view, SettingsView)
        assert view._can_edit is True

    def test_creacion_como_no_admin(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_user_session(mocker, role_name="Vendedor")
        mocker.patch(
            "opticamanager.ui.views.ajustes_view.get_iva_rate",
            return_value=Decimal("0.16"),
        )
        view = SettingsView()
        qtbot.addWidget(view)
        assert view._can_edit is False
        assert not view._iva_spin.isEnabled()

    def test_titulo_visible(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_user_session(mocker, role_name="Admin")
        mocker.patch(
            "opticamanager.ui.views.ajustes_view.get_iva_rate",
            return_value=Decimal("0.16"),
        )
        view = SettingsView()
        qtbot.addWidget(view)
        from PyQt6.QtWidgets import QLabel

        titles = view.findChildren(QLabel, "title-h1")
        assert len(titles) >= 1
        assert "Ajustes" in titles[0].text()

    def test_spin_iva_muestra_valor(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_user_session(mocker, role_name="Admin")
        mocker.patch(
            "opticamanager.ui.views.ajustes_view.get_iva_rate",
            return_value=Decimal("0.16"),
        )
        view = SettingsView()
        qtbot.addWidget(view)
        assert view._iva_spin.value() == 16.0

    def test_spin_iva_con_otro_valor(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_user_session(mocker, role_name="Admin")
        mocker.patch(
            "opticamanager.ui.views.ajustes_view.get_iva_rate",
            return_value=Decimal("0.10"),
        )
        view = SettingsView()
        qtbot.addWidget(view)
        assert view._iva_spin.value() == 10.0


# ── SettingsView Load Tests ──────────────────────────────────────────────


class TestSettingsViewLoad:
    """Tests for _load_settings."""

    def test_original_iva_se_guarda(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_user_session(mocker, role_name="Admin")
        mocker.patch(
            "opticamanager.ui.views.ajustes_view.get_iva_rate",
            return_value=Decimal("0.21"),
        )
        view = SettingsView()
        qtbot.addWidget(view)
        assert view._original_iva == Decimal("0.21")

    def test_dirty_false_al_cargar(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_user_session(mocker, role_name="Admin")
        mocker.patch(
            "opticamanager.ui.views.ajustes_view.get_iva_rate",
            return_value=Decimal("0.16"),
        )
        view = SettingsView()
        qtbot.addWidget(view)
        assert view._dirty is False


# ── SettingsView OnIvaChanged Tests ──────────────────────────────────────


class TestSettingsViewOnIvaChanged:
    """Tests for _on_iva_changed."""

    def test_valor_igual_no_muestra_boton(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        _fake_user_session(mocker, role_name="Admin")
        mocker.patch(
            "opticamanager.ui.views.ajustes_view.get_iva_rate",
            return_value=Decimal("0.16"),
        )
        view = SettingsView()
        qtbot.addWidget(view)
        # Set same value
        view._iva_spin.setValue(16.0)
        assert view._dirty is False
        assert not view._save_container.isVisible()

    def test_valor_diferente_muestra_boton(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        _fake_user_session(mocker, role_name="Admin")
        mocker.patch(
            "opticamanager.ui.views.ajustes_view.get_iva_rate",
            return_value=Decimal("0.16"),
        )
        view = SettingsView()
        qtbot.addWidget(view)
        view.show()
        view._iva_spin.setValue(21.0)
        assert view._dirty is True
        assert view._save_container.isVisible()


# ── SettingsView OnSave Tests ────────────────────────────────────────────


class TestSettingsViewOnSave:
    """Tests for _on_save."""

    def test_guardar_exitoso(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        _fake_user_session(mocker, role_name="Admin")
        mocker.patch(
            "opticamanager.ui.views.ajustes_view.get_iva_rate",
            return_value=Decimal("0.16"),
        )
        view = SettingsView()
        qtbot.addWidget(view)
        view._iva_spin.setValue(21.0)
        mock_set = mocker.patch("opticamanager.ui.views.ajustes_view.set_iva_rate")
        info_msgs: list = []
        mocker.patch.object(
            QMessageBox,
            "information",
            side_effect=lambda *_a, **_k: info_msgs.append("ok"),
        )
        view._on_save()
        mock_set.assert_called_once_with(Decimal("0.21"))
        assert view._dirty is False
        assert not view._save_container.isVisible()
        assert info_msgs

    def test_guardar_no_admin_no_hace_nada(
        self, qtbot: QtBot, mocker: MockerFixture
    ) -> None:
        _fake_user_session(mocker, role_name="Vendedor")
        mocker.patch(
            "opticamanager.ui.views.ajustes_view.get_iva_rate",
            return_value=Decimal("0.16"),
        )
        view = SettingsView()
        qtbot.addWidget(view)
        mock_set = mocker.patch("opticamanager.ui.views.ajustes_view.set_iva_rate")
        view._on_save()
        mock_set.assert_not_called()
