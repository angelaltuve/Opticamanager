"""BCV exchange rate service with manual override.

Uses pyvenezuela for BCV rate fetching (built-in 8-hour cache).
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from pyvenezuela import BCVCurrencyEnum, get_rates_by_bcv

from opticamanager.core.logging_config import get_logger

log = get_logger(__name__)

# Seconds to wait for the BCV HTTP query. The query runs on its own thread so a
# slow or hung BCV cannot block the UI. Nothing can interrupt that thread; the
# caller simply stops waiting.
BCV_TIMEOUT_SEGUNDOS = float(os.environ.get("OPTICAMANAGER_BCV_TIMEOUT", "10"))


# ── Rate info dataclass ───────────────────────────────────────────


@dataclass
class RateInfo:
    """Structured exchange rate information."""

    rate: Decimal
    source: str  # "bcv", "manual" or "unknown"
    updated_at: datetime | None

    @property
    def is_valid(self) -> bool:
        """Whether this holds a usable rate.

        A fetch failure yields ``rate == 0`` with ``source == "unknown"``; that
        sentinel must never be used as a multiplier.
        """
        return self.rate > 0


# ── Internal state ────────────────────────────────────────────────

_manual_rate: Decimal | None = None
_manual_rate_since: datetime | None = None


# ── Public API ────────────────────────────────────────────────────


def get_usd_rate() -> Decimal | None:
    """Get the current USD/BS exchange rate.

    Returns the manual override if set, otherwise uses pyvenezuela
    to fetch the BCV rate (with built-in 8-hour cache).
    """
    if _manual_rate is not None:
        log.debug("Using manual rate: 1 USD = %s Bs", _manual_rate)
        return _manual_rate

    info = _fetch_bcv_rate()
    return info.rate if info.rate and info.rate > 0 else None


def get_rate_info() -> RateInfo:
    """Get the current rate with metadata (source, timestamp).

    Returns the manual override if set, otherwise fetches from BCV
    via pyvenezuela (built-in 8-hour cache).
    """
    if _manual_rate is not None:
        return RateInfo(
            rate=_manual_rate,
            source="manual",
            updated_at=_manual_rate_since,
        )

    return _fetch_bcv_rate()


def force_refresh() -> RateInfo:
    """Clear manual override and fetch a fresh BCV rate."""
    global _manual_rate, _manual_rate_since  # noqa: PLW0603
    _manual_rate = None
    _manual_rate_since = None
    return _fetch_bcv_rate()


def set_manual_rate(rate: Decimal) -> None:
    """Set a manual exchange rate override."""
    global _manual_rate, _manual_rate_since  # noqa: PLW0603
    _manual_rate = rate
    _manual_rate_since = datetime.now()
    log.info("Manual rate set: 1 USD = %s Bs (since %s)", rate, _manual_rate_since)


def clear_manual_rate() -> None:
    """Clear the manual rate override; next call fetches from BCV again."""
    global _manual_rate, _manual_rate_since  # noqa: PLW0603
    log.info("Manual rate cleared, reverting to BCV")
    _manual_rate = None
    _manual_rate_since = None


# ── Internal helpers ──────────────────────────────────────────────


def _fetch_bcv_rate() -> RateInfo:
    """Fetch BCV rate via pyvenezuela (built-in 8h cache).

    Never raises: a failed fetch returns ``rate == 0`` with
    ``source == "unknown"``. Callers must check :attr:`RateInfo.is_valid`
    (or use :func:`get_usd_rate`, which returns ``None``) before converting.
    """
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="bcv-rate") as pool:
        future = pool.submit(get_rates_by_bcv)
        try:
            data = future.result(timeout=BCV_TIMEOUT_SEGUNDOS)
        except FutureTimeoutError:
            log.warning(
                "BCV fetch timed out after %ss; treating rate as unavailable",
                BCV_TIMEOUT_SEGUNDOS,
            )
            return _rate_unavailable("timeout")
        except Exception:
            log.exception("BCV fetch failed")
            return _rate_unavailable("error")

    if data is None or BCVCurrencyEnum.USD not in data:
        log.warning("Could not get BCV exchange rate: USD missing from response")
        return _rate_unavailable("missing")

    try:
        rate = Decimal(str(data[BCVCurrencyEnum.USD]))
    except ArithmeticError, ValueError, TypeError:
        log.exception(
            "BCV returned a non-numeric USD rate: %r", data[BCVCurrencyEnum.USD]
        )
        return _rate_unavailable("invalid_value")

    if rate <= 0:
        log.warning("BCV returned a non-positive USD rate: %s", rate)
        return _rate_unavailable("non_positive")

    log.info("Current BCV rate: 1 USD = %s Bs", rate)
    return RateInfo(
        rate=rate,
        source="bcv",
        updated_at=datetime.now(),
    )


def _rate_unavailable(reason: str) -> RateInfo:
    """Build the sentinel used when no usable BCV rate could be obtained."""
    log.debug("BCV rate unavailable (reason=%s)", reason)
    return RateInfo(rate=Decimal("0"), source="unknown", updated_at=None)


# ── Converters ────────────────────────────────────────────────────


def convert_to_usd(bolivares: Decimal, rate: Decimal | None = None) -> Decimal | None:
    """Convert bolivares to USD, or return None when no usable rate exists."""
    if rate is None:
        rate = get_usd_rate()
    if rate is None or rate <= 0:
        log.error("Cannot convert: invalid rate (%s)", rate)
        return None
    result = bolivares / rate
    log.debug("%s Bs -> %s USD (rate: %s)", bolivares, result, rate)
    return result


def convert_to_bs(dollars: Decimal, rate: Decimal | None = None) -> Decimal | None:
    """Convert USD to bolivares, or return None when no usable rate exists.

    A zero or negative rate returns None instead of silently yielding 0 Bs.
    """
    if rate is None:
        rate = get_usd_rate()
    if rate is None or rate <= 0:
        log.error("Cannot convert: invalid rate (%s)", rate)
        return None
    result = dollars * rate
    log.debug("%s USD -> %s Bs (rate: %s)", dollars, result, rate)
    return result
