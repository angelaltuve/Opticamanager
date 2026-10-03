"""Tests for the settings service (settings_service) against the real DB."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel import select

from opticamanager.db import SessionManager
from opticamanager.models.app_setting import AppSetting
from opticamanager.services import settings_service


class TestIvaRate:
    def test_get_iva_rate_default_cuando_no_existe(self) -> None:
        # Ensure no iva_rate row exists before asserting the default.
        with SessionManager() as session:
            for s in session.exec(select(AppSetting)).all():
                if s.key == "iva_rate":
                    session.delete(s)
            session.commit()

        assert settings_service.get_iva_rate() == Decimal("0.16")
        assert settings_service.get_iva_rate_pct() == 16

    def test_set_y_get_iva_rate(self) -> None:
        settings_service.set_iva_rate(Decimal("0.21"))

        assert settings_service.get_iva_rate() == Decimal("0.21")
        assert settings_service.get_iva_rate_pct() == 21

        # Persisted with the expected description.
        with SessionManager() as session:
            setting = session.exec(
                select(AppSetting).where(AppSetting.key == "iva_rate")
            ).first()
            assert setting is not None
            assert setting.value == "0.21"
            assert "IVA" in (setting.description or "")

    def test_set_actualiza_valor_existente(self) -> None:
        settings_service.set_iva_rate(Decimal("0.16"))
        settings_service.set_iva_rate(Decimal("0.25"))

        assert settings_service.get_iva_rate() == Decimal("0.25")

    def test_set_iva_rate_rechaza_fuera_de_rango(self) -> None:
        with pytest.raises(ValueError, match="entre 0 y 1"):
            settings_service.set_iva_rate(Decimal("1.5"))
        with pytest.raises(ValueError, match="entre 0 y 1"):
            settings_service.set_iva_rate(Decimal("-0.01"))

    def test_set_iva_rate_acepta_los_extremos(self) -> None:
        settings_service.set_iva_rate(Decimal("0"))
        assert settings_service.get_iva_rate() == Decimal("0")
        settings_service.set_iva_rate(Decimal("1"))
        assert settings_service.get_iva_rate() == Decimal("1")
        settings_service.set_iva_rate(Decimal("0.16"))

    def test_get_iva_rate_pct_redondea_en_lugar_de_truncar(self) -> None:
        # Before: int(0.165 * 100) == 16 (truncation). It must report 17 now.
        settings_service.set_iva_rate(Decimal("0.165"))
        assert settings_service.get_iva_rate_pct() == 17

    def test_get_iva_rate_valor_corrupto_usa_default(self) -> None:
        with SessionManager() as session:
            setting = session.exec(
                select(AppSetting).where(AppSetting.key == "iva_rate")
            ).first()
            if setting is None:
                setting = AppSetting(key="iva_rate", value="abc")
                session.add(setting)
            else:
                setting.value = "abc"
            session.commit()

        assert settings_service.get_iva_rate() == Decimal("0.16")
        assert settings_service.get_iva_rate_pct() == 16
