"""Tests for the logging utilities re-export (utils/logger.py)."""

from __future__ import annotations

import importlib
import sys

from opticamanager.core import logging_config
from opticamanager.utils import logger as logger_utils


class TestLoggerUtils:
    def test_reexports_get_logger_y_setup_logging(self) -> None:
        assert logger_utils.get_logger is logging_config.get_logger
        assert logger_utils.setup_logging is logging_config.setup_logging
        assert set(logger_utils.__all__) == {"get_logger", "setup_logging"}

    def test_excepthook_instalado_al_importar(self) -> None:
        # pytest swaps sys.excepthook when the test session starts, so re-run
        # the module to observe the import side effect.
        importlib.reload(logger_utils)
        assert sys.excepthook is logger_utils._global_excepthook

    def test_global_excepthook_registra_critical(self, caplog) -> None:
        try:
            raise ValueError("boom de prueba")
        except ValueError:
            exc_type, exc_val, exc_tb = sys.exc_info()

        with caplog.at_level("CRITICAL", logger="opticamanager"):
            logger_utils._global_excepthook(exc_type, exc_val, exc_tb)

        assert any(
            r.levelname == "CRITICAL"
            and "ValueError" in r.message
            and "boom de prueba" in r.message
            and "test_logger_utils" in r.message
            for r in caplog.records
        )
