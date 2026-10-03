import sys
import traceback
from typing import Any

from opticamanager.core.logging_config import get_logger, setup_logging

__all__ = ["get_logger", "setup_logging"]


def _global_excepthook(
    exc_type: type[BaseException],
    exc_val: BaseException,
    exc_tb: Any,
) -> None:
    logger = get_logger("opticamanager")
    logger.critical(
        "Excepción no capturada: %s: %s\n%s",
        exc_type.__name__,
        exc_val,
        "".join(traceback.format_tb(exc_tb)),
    )


sys.excepthook = _global_excepthook
