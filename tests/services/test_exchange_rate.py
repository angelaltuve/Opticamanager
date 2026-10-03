"""Tests for the BCV exchange rate service (exchange_rate).

The network (pyvenezuela) is always mocked; the module's manual-rate
state is reset between tests to avoid cross-test leakage.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from decimal import Decimal

import pytest
from pytest_mock import MockerFixture

from opticamanager.services import exchange_rate

USD = exchange_rate.BCVCurrencyEnum.USD


@pytest.fixture(autouse=True)
def _reset_manual_rate() -> Generator[None, None, None]:
    exchange_rate._manual_rate = None
    exchange_rate._manual_rate_since = None
    yield
    exchange_rate._manual_rate = None
    exchange_rate._manual_rate_since = None


class TestGetUsdRate:
    def test_devolver_tasa_manual_sin_tocar_red(self, mocker: MockerFixture) -> None:
        fetch = mocker.patch("opticamanager.services.exchange_rate._fetch_bcv_rate")
        exchange_rate.set_manual_rate(Decimal("36.50"))

        assert exchange_rate.get_usd_rate() == Decimal("36.50")
        fetch.assert_not_called()

    def test_fetch_bcv_con_tasa_valida(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.services.exchange_rate.get_rates_by_bcv",
            return_value={USD: 36.54},
        )

        assert exchange_rate.get_usd_rate() == Decimal("36.54")

    def test_fetch_devuelve_none_si_no_hay_data(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.services.exchange_rate.get_rates_by_bcv",
            return_value=None,
        )

        assert exchange_rate.get_usd_rate() is None

    def test_fetch_devuelve_none_si_falta_usd(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.services.exchange_rate.get_rates_by_bcv",
            return_value={},
        )

        assert exchange_rate.get_usd_rate() is None

    def test_fetch_devuelve_none_si_tasa_cero(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.services.exchange_rate.get_rates_by_bcv",
            return_value={USD: 0},
        )

        assert exchange_rate.get_usd_rate() is None

    def test_fetch_excepcion_devuelve_none(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.services.exchange_rate.get_rates_by_bcv",
            side_effect=RuntimeError("red caida"),
        )

        assert exchange_rate.get_usd_rate() is None


class TestGetRateInfo:
    def test_info_manual_con_timestamp(self) -> None:
        exchange_rate.set_manual_rate(Decimal("37.10"))

        info = exchange_rate.get_rate_info()

        assert info.rate == Decimal("37.10")
        assert info.source == "manual"
        assert isinstance(info.updated_at, datetime)

    def test_info_bcv(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.services.exchange_rate.get_rates_by_bcv",
            return_value={USD: 36.54},
        )

        info = exchange_rate.get_rate_info()

        assert info.rate == Decimal("36.54")
        assert info.source == "bcv"
        assert isinstance(info.updated_at, datetime)

    def test_info_desconocida_si_falla(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "opticamanager.services.exchange_rate.get_rates_by_bcv",
            return_value=None,
        )

        info = exchange_rate.get_rate_info()

        assert info.rate == Decimal("0")
        assert info.source == "unknown"
        assert info.updated_at is None


class TestForceRefreshAndClear:
    def test_force_refresh_limpia_manual_y_fetch(self, mocker: MockerFixture) -> None:
        fetch = mocker.patch(
            "opticamanager.services.exchange_rate.get_rates_by_bcv",
            return_value={USD: 38.00},
        )
        exchange_rate.set_manual_rate(Decimal("50.00"))

        info = exchange_rate.force_refresh()

        assert exchange_rate._manual_rate is None
        assert exchange_rate._manual_rate_since is None
        fetch.assert_called_once()
        assert info.rate == Decimal("38.00")

    def test_clear_manual_rate_restaura_bcv(self, mocker: MockerFixture) -> None:
        fetch = mocker.patch(
            "opticamanager.services.exchange_rate.get_rates_by_bcv",
            return_value={USD: 39.00},
        )
        exchange_rate.set_manual_rate(Decimal("99.99"))

        exchange_rate.clear_manual_rate()

        assert exchange_rate.get_usd_rate() == Decimal("39.00")
        fetch.assert_called_once()


class TestConverters:
    def test_convert_to_usd_con_tasa_explicita(self) -> None:
        assert exchange_rate.convert_to_usd(
            Decimal("100"), Decimal("36.50")
        ) == Decimal("100") / Decimal("36.50")

    def test_convert_to_usd_usa_tasa_de_get_usd_rate(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.services.exchange_rate.get_usd_rate",
            return_value=Decimal("40"),
        )

        assert exchange_rate.convert_to_usd(Decimal("400")) == Decimal("10")

    def test_convert_to_usd_tasa_invalida_devuelve_none(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.services.exchange_rate.get_usd_rate", return_value=None
        )
        assert exchange_rate.convert_to_usd(Decimal("100")) is None

    def test_convert_to_usd_tasa_cero_devuelve_none(self) -> None:
        assert exchange_rate.convert_to_usd(Decimal("100"), Decimal("0")) is None

    def test_convert_to_bs_con_tasa_explicita(self) -> None:
        assert exchange_rate.convert_to_bs(Decimal("10"), Decimal("36.50")) == Decimal(
            "365.00"
        )

    def test_convert_to_bs_usa_tasa_de_get_usd_rate(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.services.exchange_rate.get_usd_rate",
            return_value=Decimal("40"),
        )

        assert exchange_rate.convert_to_bs(Decimal("10")) == Decimal("400")

    def test_convert_to_bs_tasa_invalida_devuelve_none(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.services.exchange_rate.get_usd_rate", return_value=None
        )
        assert exchange_rate.convert_to_bs(Decimal("10")) is None

    def test_convert_to_bs_tasa_cero_devuelve_none(self) -> None:
        """Regression: a zero rate used to return 0 Bs instead of None."""
        assert exchange_rate.convert_to_bs(Decimal("10"), Decimal("0")) is None

    def test_convert_to_bs_tasa_negativa_devuelve_none(self) -> None:
        assert exchange_rate.convert_to_bs(Decimal("10"), Decimal("-36")) is None

    def test_convert_to_usd_tasa_negativa_devuelve_none(self) -> None:
        assert exchange_rate.convert_to_usd(Decimal("100"), Decimal("-36")) is None


class TestRateUnavailable:
    """The sentinel returned on failure must never be usable as a multiplier."""

    def test_rate_info_is_valid_reflects_bcv_rate(self) -> None:
        assert exchange_rate.RateInfo(Decimal("36"), "bcv", None).is_valid is True

    def test_rate_info_no_valida_tasa_cero(self) -> None:
        assert exchange_rate.RateInfo(Decimal("0"), "unknown", None).is_valid is False

    def test_rate_info_no_valida_tasa_negativa(self) -> None:
        assert exchange_rate.RateInfo(Decimal("-1"), "unknown", None).is_valid is False

    def test_fetch_timed_out_marca_no_disponible(self, mocker: MockerFixture) -> None:
        """A slow BCV must not block the caller forever."""

        def _never(*_args: object, **_kwargs: object) -> None:
            import time

            time.sleep(5)

        mocker.patch("opticamanager.services.exchange_rate.get_rates_by_bcv", _never)
        mocker.patch("opticamanager.services.exchange_rate.BCV_TIMEOUT_SEGUNDOS", 0.05)

        info = exchange_rate.get_rate_info()

        assert info.is_valid is False
        assert info.source == "unknown"

    def test_fetch_tasa_no_numerica_marca_no_disponible(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.services.exchange_rate.get_rates_by_bcv",
            return_value={exchange_rate.BCVCurrencyEnum.USD: "no-es-un-numero"},
        )

        info = exchange_rate.get_rate_info()

        assert info.is_valid is False
        assert info.source == "unknown"

    def test_fetch_tasa_negativa_marca_no_disponible(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.services.exchange_rate.get_rates_by_bcv",
            return_value={exchange_rate.BCVCurrencyEnum.USD: -5},
        )

        assert exchange_rate.get_rate_info().is_valid is False

    def test_get_usd_rate_devuelve_none_cuando_no_hay_tasa(
        self, mocker: MockerFixture
    ) -> None:
        mocker.patch(
            "opticamanager.services.exchange_rate.get_rates_by_bcv",
            return_value=None,
        )
        assert exchange_rate.get_usd_rate() is None
