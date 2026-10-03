from __future__ import annotations

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Final

import urllib3
from urllib3.exceptions import InsecureRequestWarning

LOG_DIR: Final = Path(__file__).resolve().parent.parent.parent.parent / "logs"
LOG_FILE: Final = LOG_DIR / "opticamanager.log"
LOG_MAX_BYTES: Final = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT: Final = 5
LOG_LEVEL_ENV: Final = os.getenv("OPTICA_LOG_LEVEL", "DEBUG").upper()
CONSOLE_LEVEL_ENV: Final = os.getenv("OPTICA_CONSOLE_LEVEL", "INFO").upper()

_FILE_FORMAT: Final = "%(asctime)s.%(msecs)03d [%(levelname)-8s] %(name)-25s %(funcName)-20s L%(lineno)-4d %(message)s"
_CONSOLE_FORMAT: Final = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
_DATE_FORMAT: Final = "%Y-%m-%d %H:%M:%S"

_SENSITIVE_PATTERNS: Final[list[re.Pattern]] = [
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(Authorization|Bearer)\s+\S+"),
]

_loggers_configured: set[str] = set()


def _redact_sensitive(record: logging.LogRecord) -> str:
    msg = record.getMessage()
    for pattern in _SENSITIVE_PATTERNS:
        msg = pattern.sub(r"\1=****", msg)
    return msg


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.msg = _redact_sensitive(record)
        record.args = None
        return super().format(record)


class LevelFilter(logging.Filter):
    def __init__(self, min_level: int, max_level: int) -> None:
        super().__init__()
        self.min_level = min_level
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return self.min_level <= record.levelno <= self.max_level


def _context_location(context: Any) -> str:
    """Render the source position of a Qt message as a bracketed suffix.

    ``QMessageLogContext`` exposes ``file`` and ``line`` as plain attributes, not
    methods. Calling them raised ``TypeError: 'NoneType' object is not callable``
    on every Qt log line, which aborted the handler before it reached ``log_fn``
    and dropped the message.
    """
    if context is None:
        return ""
    filename = getattr(context, "file", None)
    if not filename:
        return ""
    line = getattr(context, "line", None)
    return f" [{filename}:{line}]" if line else f" [{filename}]"


def _severity_for(mtype: Any, logger: logging.Logger) -> Callable[..., None]:
    """Resolve a Qt message type to the logging callable that matches it.

    PyQt6 6.x passes a ``QtMsgType`` enum member, older releases passed a bare
    int. The table used to be keyed on plain ints, so it missed every enum member
    and sent all Qt output to INFO, which a WARNING console level then filtered
    out. Unwrapping ``.value`` accepts both shapes.
    """
    value = getattr(mtype, "value", mtype)
    if not isinstance(value, int):
        return logger.info
    table = {
        0: logger.debug,
        1: logger.warning,
        2: logger.critical,
        3: logger.error,
        4: logger.info,
    }
    return table.get(value, logger.info)


def qt_handler(mtype: int, context: Any, message: str) -> None:
    """Route a Qt message to the ``qt`` logger at the matching severity.

    Kept at module level so it can be exercised without installing a handler.
    """
    logger = logging.getLogger("qt")
    msg = message.strip()
    if not msg:
        return
    _severity_for(mtype, logger)("%s%s", msg, _context_location(context))


def _setup_qt_logging() -> None:
    try:
        from PyQt6.QtCore import qInstallMessageHandler

        qInstallMessageHandler(qt_handler)  # type: ignore[arg-type]
    except ImportError:
        pass


def _capture_warnings() -> None:
    logging.captureWarnings(True)
    warnings_logger = logging.getLogger("py.warnings")
    warnings_logger.setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def setup_logging(
    log_level: str | int = LOG_LEVEL_ENV,
    console_level: str | int = CONSOLE_LEVEL_ENV,
    log_file: Path = LOG_FILE,
    max_bytes: int = LOG_MAX_BYTES,
    backup_count: int = LOG_BACKUP_COUNT,
) -> None:
    if isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper(), logging.DEBUG)
    if isinstance(console_level, str):
        console_level = getattr(logging, console_level.upper(), logging.INFO)

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(RedactingFormatter(_FILE_FORMAT, _DATE_FORMAT))
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(RedactingFormatter(_CONSOLE_FORMAT, _DATE_FORMAT))
    root_logger.addHandler(console_handler)

    _capture_warnings()
    # BCV (via pyvenezuela) intentionally uses verify=False against a
    # self-signed endpoint; silence urllib3's InsecureRequestWarning.
    urllib3.disable_warnings(InsecureRequestWarning)
    _setup_qt_logging()

    get_logger(__name__).info(
        "Logging initialized | file=%s level=%s console=%s",
        log_file,
        logging.getLevelName(log_level),
        logging.getLevelName(console_level),
    )
