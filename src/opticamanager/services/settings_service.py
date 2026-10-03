"""AppSettings service: read/write global configuration values."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlmodel import select

from opticamanager.core.logging_config import get_logger
from opticamanager.db import SessionManager
from opticamanager.models.app_setting import AppSetting

log = get_logger(__name__)

# ── Helpers ──────────────────────────────────────────────────


def _get_setting(key: str, default: str = "") -> str:
    """Read a setting value from DB, returning *default* if missing."""
    with SessionManager() as session:
        setting = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
        if setting is None:
            return default
        return setting.value


def _set_setting(key: str, value: str, description: str | None = None) -> None:
    """Create or update a setting value."""
    with SessionManager() as session:
        setting = session.exec(select(AppSetting).where(AppSetting.key == key)).first()
        if setting is None:
            setting = AppSetting(key=key, value=value, description=description)
            session.add(setting)
        else:
            setting.value = value
            if description is not None:
                setting.description = description
        session.commit()
        log.info("Setting %s = %s", key, value)


# ── IVA rate ─────────────────────────────────────────────────

_IVA_DEFAULT = Decimal("0.16")


def get_iva_rate() -> Decimal:
    """Return the current IVA rate (e.g. 0.16 = 16%)."""
    raw = _get_setting("iva_rate", str(_IVA_DEFAULT))
    try:
        return Decimal(raw)
    except InvalidOperation:
        log.warning("Invalid iva_rate '%s', using default %s", raw, _IVA_DEFAULT)
        return _IVA_DEFAULT


def set_iva_rate(rate: Decimal) -> None:
    """Persist a new IVA rate.

    Raises:
        ValueError: if *rate* is outside 0..1 (0%..100%).
    """
    if not Decimal(0) <= rate <= Decimal(1):
        raise ValueError(
            f"La tasa de IVA debe estar entre 0 y 1 (0%..100%); se recibió {rate}."
        )
    _set_setting("iva_rate", str(rate), "Tasa de IVA (ej: 0.16 = 16%)")


def get_iva_rate_pct() -> int:
    """Return IVA rate as integer percentage (e.g. 16 for 0.16).

    Round half up instead of truncating, so a rate of 0.165 reports as 17%
    rather than 16%.
    """
    pct = get_iva_rate() * 100
    return int(pct.quantize(Decimal(1), rounding=ROUND_HALF_UP))
