"""Smoke tests for DashboardBIView: KPI cards, date filters, and refresh button."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import QDateEdit, QPushButton
from pytest_mock import MockerFixture

from opticamanager.ui.views.dashboard_bi_view import DashboardBIView, _KPICard

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


class TestDashboardBIView:
    """Smoke tests for the BI dashboard view."""

    def test_creation(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        """View creates without error and has 4 KPI cards."""
        mocker.patch.object(DashboardBIView, "_refresh", return_value=None)
        view = DashboardBIView()
        qtbot.addWidget(view)
        assert isinstance(view, DashboardBIView)
        assert len(view._cards) == 4

    def test_kpi_cards_exist(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        """All 4 KPI cards are _KPICard instances with expected keys."""
        mocker.patch.object(DashboardBIView, "_refresh", return_value=None)
        view = DashboardBIView()
        qtbot.addWidget(view)
        expected = {
            "ventas_hoy",
            "ventas_mes",
            "productos",
            "stock_bajo",
        }
        assert set(view._cards) == expected
        for card in view._cards.values():
            assert isinstance(card, _KPICard)

    def test_date_filters_exist(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        """QDateEdit widgets exist with correct default dates."""
        mocker.patch.object(DashboardBIView, "_refresh", return_value=None)
        view = DashboardBIView()
        qtbot.addWidget(view)
        assert isinstance(view._date_from, QDateEdit)
        assert isinstance(view._date_to, QDateEdit)
        assert view._date_to.date() == QDate.currentDate()
        assert view._date_from.date() == QDate.currentDate().addMonths(-1)

    def test_actualizar_button(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        """'Actualizar' button exists and triggers _refresh on click."""
        mock_refresh = mocker.patch.object(
            DashboardBIView, "_refresh", return_value=None
        )
        view = DashboardBIView()
        qtbot.addWidget(view)
        button = view.findChild(QPushButton)
        assert button is not None
        assert "Actualizar" in button.text()
        mock_refresh.reset_mock()
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        mock_refresh.assert_called_once()

    def test_creation_with_data(self, qtbot: QtBot, mocker: MockerFixture) -> None:
        """Mock _refresh, manually set KPI values, verify labels update."""
        mocker.patch.object(DashboardBIView, "_refresh", return_value=None)
        view = DashboardBIView()
        qtbot.addWidget(view)
        view._cards["ventas_hoy"].set_value("Bs. 1,500.00")
        assert "1,500" in view._cards["ventas_hoy"]._value.text()
        view._cards["stock_bajo"].set_value("3")
        assert view._cards["stock_bajo"]._value.text() == "3"
