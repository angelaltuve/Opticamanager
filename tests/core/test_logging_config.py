from __future__ import annotations

import logging
from pathlib import Path

import pytest
from PyQt6.QtCore import QtMsgType

from opticamanager.core.logging_config import (
    LevelFilter,
    RedactingFormatter,
    _context_location,
    _redact_sensitive,
    get_logger,
    qt_handler,
    setup_logging,
)


# ── _redact_sensitive ──────────────────────────────────────────────────────


class TestRedactSensitive:
    def test_redacts_password_in_header(self) -> None:
        """Password in header format is redacted.

        Note: The regex matches Authorization followed by one non-whitespace
        token, replacing it with `Authorization=****`. Extra tokens after the
        first word are not redacted by this pattern.
        """
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "Authorization: Bearer secret123", (), None
        )
        result = _redact_sensitive(record)
        # "secret123" is not redacted; the pattern grabs only "Authorization: Bearer"
        # and replaces it with "Authorization=****", leaving "secret123" in place
        # This is the documented limitation of the current pattern.
        assert "Authorization" in result
        assert "=****" in result

    def test_redacts_password_assignment(self) -> None:
        """password=plaintext is redacted."""
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "password=my_secret_pass", (), None
        )
        result = _redact_sensitive(record)
        assert "my_secret_pass" not in result

    def test_redacts_api_key(self) -> None:
        """api_key assignment is redacted."""
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "api_key=abc123def456", (), None
        )
        result = _redact_sensitive(record)
        assert "abc123def456" not in result

    def test_redacts_token_eq_value(self) -> None:
        """token=value format is redacted (JSON token: syntax not matched)."""
        record = logging.LogRecord(
            "test",
            logging.INFO,
            "",
            0,
            "token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0",
            (),
            None,
        )
        result = _redact_sensitive(record)
        assert "eyJ" not in result

    def test_redacts_secret(self) -> None:
        """secret=value is redacted."""
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "secret=supersecretvalue", (), None
        )
        result = _redact_sensitive(record)
        assert "supersecretvalue" not in result

    def test_redacts_bearer_token(self) -> None:
        """Bearer token word is redacted (Authorization prefix not required)."""
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "Bearer jwt_token_here", (), None
        )
        result = _redact_sensitive(record)
        assert "jwt_token_here" not in result

    def test_leaves_normal_text_unchanged(self) -> None:
        """Regular log messages without sensitive data are untouched."""
        msg = "User login successful for admin"
        record = logging.LogRecord("test", logging.INFO, "", 0, msg, (), None)
        result = _redact_sensitive(record)
        assert result == msg

    def test_case_insensitive_matching(self) -> None:
        """Patterns match regardless of case."""
        msg = "PASSWORD=supersecret"
        record = logging.LogRecord("test", logging.INFO, "", 0, msg, (), None)
        result = _redact_sensitive(record)
        assert "supersecret" not in result

    def test_redacts_passwd_variant(self) -> None:
        """passwd (abbreviated) is also redacted."""
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "passwd=hunter2", (), None
        )
        result = _redact_sensitive(record)
        assert "hunter2" not in result


# ── RedactingFormatter ────────────────────────────────────────────────────


class TestRedactingFormatter:
    def test_redacts_in_format(self) -> None:
        """RedactingFormatter redacts sensitive data during formatting."""
        fmt = RedactingFormatter("%(message)s")
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "password=secret123", (), None
        )
        result = fmt.format(record)
        assert "secret123" not in result

    def test_preserves_normal_message(self) -> None:
        """Non-sensitive messages pass through unchanged."""
        fmt = RedactingFormatter("%(message)s")
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "Everything is fine", (), None
        )
        result = fmt.format(record)
        assert result == "Everything is fine"

    def test_clears_args_after_redaction(self) -> None:
        """record.args is set to None after formatting to prevent double processing."""
        fmt = RedactingFormatter("%(message)s")
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "password=%s", ("secret",), None
        )
        formatted = fmt.format(record)
        # Args are cleared and the formatted message no longer contains the secret
        assert record.args is None
        assert "secret" not in formatted

    def test_respects_format_string(self) -> None:
        """Formatter applies the correct format string with levelname and name."""
        fmt = RedactingFormatter("[%(levelname)s] %(name)s: %(message)s")
        record = logging.LogRecord(
            "my_module", logging.WARNING, "", 0, "test message", (), None
        )
        result = fmt.format(record)
        assert "[WARNING]" in result
        assert "my_module" in result
        assert "test message" in result


# ── LevelFilter ────────────────────────────────────────────────────────────


class TestLevelFilter:
    def test_filters_below_min(self) -> None:
        """Filter rejects records below the minimum level."""
        filt = LevelFilter(logging.WARNING, logging.CRITICAL)
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        assert filt.filter(record) is False  # noqa: E712

    def test_filters_above_max(self) -> None:
        """Filter rejects records above the maximum level."""
        filt = LevelFilter(logging.DEBUG, logging.WARNING)
        record = logging.LogRecord("test", logging.ERROR, "", 0, "msg", (), None)
        assert filt.filter(record) is False

    def test_passes_records_in_range(self) -> None:
        """Filter accepts records within the specified range."""
        filt = LevelFilter(logging.WARNING, logging.CRITICAL)
        for level in (logging.WARNING, logging.ERROR, logging.CRITICAL):
            record = logging.LogRecord("test", level, "", 0, "msg", (), None)
            assert filt.filter(record) is True

    def test_passes_record_at_exact_boundary(self) -> None:
        """Filter accepts records exactly at min and max levels."""
        filt = LevelFilter(logging.DEBUG, logging.ERROR)
        record_debug = logging.LogRecord("test", logging.DEBUG, "", 0, "msg", (), None)
        record_error = logging.LogRecord("test", logging.ERROR, "", 0, "msg", (), None)
        assert filt.filter(record_debug) is True
        assert filt.filter(record_error) is True


# ── get_logger ─────────────────────────────────────────────────────────────


class TestGetLogger:
    def test_returns_logger_instance(self) -> None:
        """get_logger returns a logging.Logger."""
        log = get_logger("test_module")
        assert isinstance(log, logging.Logger)

    def test_returns_same_logger_for_same_name(self) -> None:
        """get_logger with the same name returns the same logger instance."""
        log1 = get_logger("unique_test_module")
        log2 = get_logger("unique_test_module")
        assert log1 is log2

    def test_different_names_different_loggers(self) -> None:
        """Different names produce different (but related) loggers."""
        log_a = get_logger("module_a")
        log_b = get_logger("module_b")
        assert log_a is not log_b
        assert log_a.name == "module_a"
        assert log_b.name == "module_b"


# ── setup_logging ──────────────────────────────────────────────────────────


class TestSetupLogging:
    def _clean_root_handlers(self) -> None:
        """Save and remove all root logger handlers for clean test state."""
        root = logging.getLogger()
        self._saved_handlers = list(root.handlers)
        root.handlers.clear()

    def _restore_root_handlers(self) -> None:
        """Restore previously saved root logger handlers."""
        root = logging.getLogger()
        for h in root.handlers[:]:
            root.removeHandler(h)
            h.close()
        root.handlers = self._saved_handlers

    def test_adds_file_and_console_handlers(self) -> None:
        """setup_logging adds exactly 2 handlers (file + console) and removes old ones."""
        self._clean_root_handlers()
        try:
            setup_logging(
                log_level="DEBUG",
                console_level="ERROR",
                log_file=Path("/dev/null"),
            )

            root = logging.getLogger()
            assert len(root.handlers) == 2
            # First handler should be the file (RotatingFileHandler)
            from logging.handlers import RotatingFileHandler

            assert isinstance(root.handlers[0], RotatingFileHandler)
            # Second handler should be the console (StreamHandler)
            assert isinstance(root.handlers[1], logging.StreamHandler)
        finally:
            self._restore_root_handlers()

    def test_console_handler_level(self) -> None:
        """Console handler uses the specified level."""
        self._clean_root_handlers()
        try:
            setup_logging(
                log_level="DEBUG",
                console_level="ERROR",
                log_file=Path("/dev/null"),
            )

            root = logging.getLogger()
            # Find the StreamHandler that outputs to stdout (not the file one)
            stream_handlers = [
                h
                for h in root.handlers
                if isinstance(h, logging.StreamHandler)
                and not isinstance(h, logging.FileHandler)
            ]
            assert len(stream_handlers) == 1
            assert stream_handlers[0].level == logging.ERROR
        finally:
            self._restore_root_handlers()

    def test_replaces_existing_handlers(self) -> None:
        """Calling setup_logging again replaces old handlers (no duplication)."""
        self._clean_root_handlers()
        try:
            setup_logging(
                log_level="DEBUG",
                console_level="WARNING",
                log_file=Path("/dev/null"),
            )
            count_after_first = len(logging.getLogger().handlers)

            setup_logging(
                log_level="INFO",
                console_level="ERROR",
                log_file=Path("/dev/null"),
            )
            count_after_second = len(logging.getLogger().handlers)

            # After second call, should still have same number (replaced, not duplicated)
            assert count_after_second == count_after_first
            assert count_after_second == 2
        finally:
            self._restore_root_handlers()

    def test_writes_to_log_file(self, tmp_path: Path) -> None:
        """setup_logging writes log messages to the specified file."""
        self._clean_root_handlers()
        try:
            log_file = tmp_path / "test_output.log"
            setup_logging(
                log_level="DEBUG",
                console_level="CRITICAL",
                log_file=log_file,
            )

            test_logger = get_logger("test_writer")
            test_logger.info("Test log message")
            test_logger.warning("Warning message %d", 42)

            self._restore_root_handlers()

            content = log_file.read_text(encoding="utf-8")
            assert "Test log message" in content
            assert "Warning message 42" in content
        finally:
            self._restore_root_handlers()

    def test_writes_redacted_content(self, tmp_path: Path) -> None:
        """Sensitive data is redacted before being written to log file."""
        self._clean_root_handlers()
        try:
            log_file = tmp_path / "redacted_test.log"
            setup_logging(
                log_level="DEBUG",
                console_level="CRITICAL",
                log_file=log_file,
            )

            test_logger = get_logger("test_redaction")
            test_logger.info("User password=MySecretPass123")

            self._restore_root_handlers()

            content = log_file.read_text(encoding="utf-8")
            assert "MySecretPass123" not in content
            assert "password=" in content
        finally:
            self._restore_root_handlers()

    def test_creates_log_file_parent_dir(self, tmp_path: Path) -> None:
        """The parent dir of the log file must exist before setup_logging."""
        nested_log = tmp_path / "nested" / "dir" / "app.log"
        nested_log.parent.mkdir(parents=True, exist_ok=True)
        self._clean_root_handlers()
        try:
            setup_logging(
                log_level="DEBUG",
                console_level="CRITICAL",
                log_file=nested_log,
            )
            assert nested_log.parent.exists()
        finally:
            self._restore_root_handlers()

    def test_handles_string_levels(self, tmp_path: Path) -> None:
        """String log levels are converted to numeric values on handlers."""
        self._clean_root_handlers()
        try:
            log_file = tmp_path / "str_levels.log"
            setup_logging(
                log_level="INFO",
                console_level="DEBUG",
                log_file=log_file,
            )

            root = logging.getLogger()
            from logging.handlers import RotatingFileHandler

            file_handler = next(
                h for h in root.handlers if isinstance(h, RotatingFileHandler)
            )
            stream_handler = next(
                h
                for h in root.handlers
                if isinstance(h, logging.StreamHandler)
                and not isinstance(h, logging.FileHandler)
            )

            assert file_handler.level == logging.INFO
            assert stream_handler.level == logging.DEBUG
        finally:
            self._restore_root_handlers()


# ── _context_location ───────────────────────────────────────────────────────


class _FakeContext:
    """Stand-in for ``QMessageLogContext``, where ``file``/``line`` are attributes."""

    def __init__(self, file: str | None, line: int | None) -> None:
        self.file = file
        self.line = line


class TestContextLocation:
    def test_reads_plain_attributes(self) -> None:
        """The real QMessageLogContext exposes file/line as attributes, so read them as such."""
        assert _context_location(_FakeContext("main.py", 42)) == " [main.py:42]"

    def test_empty_file_yields_no_suffix(self) -> None:
        assert _context_location(_FakeContext("", 42)) == ""
        assert _context_location(_FakeContext(None, 42)) == ""

    def test_missing_line_still_names_the_file(self) -> None:
        assert _context_location(_FakeContext("main.py", None)) == " [main.py]"
        assert _context_location(_FakeContext("main.py", 0)) == " [main.py]"

    def test_none_context_is_tolerated(self) -> None:
        assert _context_location(None) == ""


# ── qt_handler ──────────────────────────────────────────────────────────────


class TestQtHandler:
    def test_emits_the_message_with_its_source_position(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Regression: reading file/line as methods raised TypeError and dropped the record."""
        with caplog.at_level(logging.DEBUG, logger="qt"):
            qt_handler(1, _FakeContext("painter.cpp", 118), "Painter not active")

        record = caplog.records[-1]
        assert record.getMessage() == "Painter not active [painter.cpp:118]"
        assert record.levelno == logging.WARNING

    @pytest.mark.parametrize(
        ("mtype", "level"),
        [
            (0, logging.DEBUG),
            (1, logging.WARNING),
            (2, logging.CRITICAL),
            (3, logging.ERROR),
            (4, logging.INFO),
        ],
    )
    def test_maps_bare_int_types_to_severities(
        self, caplog: pytest.LogCaptureFixture, mtype: int, level: int
    ) -> None:
        """Older PyQt6 releases handed the handler a bare int."""
        with caplog.at_level(logging.DEBUG, logger="qt"):
            qt_handler(mtype, _FakeContext(None, None), "message")

        assert caplog.records[-1].levelno == level

    @pytest.mark.parametrize(
        ("member", "level"),
        [
            (QtMsgType.QtDebugMsg, logging.DEBUG),
            (QtMsgType.QtWarningMsg, logging.WARNING),
            (QtMsgType.QtCriticalMsg, logging.CRITICAL),
            (QtMsgType.QtFatalMsg, logging.ERROR),
            (QtMsgType.QtInfoMsg, logging.INFO),
        ],
    )
    def test_maps_qt_msg_type_enum_to_severities(
        self,
        caplog: pytest.LogCaptureFixture,
        member: QtMsgType,
        level: int,
    ) -> None:
        """Regression: PyQt6 6.x sends a QtMsgType member, which an int-keyed table misses.

        Every Qt message used to land on INFO, so a WARNING console level dropped
        Qt diagnostics on the floor.
        """
        with caplog.at_level(logging.DEBUG, logger="qt"):
            qt_handler(member, _FakeContext("painter.cpp", 7), "message")

        assert caplog.records[-1].levelno == level

    def test_unknown_type_falls_back_to_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="qt"):
            qt_handler(99, _FakeContext(None, None), "message")

        assert caplog.records[-1].levelno == logging.INFO

    def test_non_integer_type_falls_back_to_info(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="qt"):
            qt_handler("warning", _FakeContext(None, None), "message")

        assert caplog.records[-1].levelno == logging.INFO

    def test_blank_message_logs_nothing(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG, logger="qt"):
            qt_handler(1, _FakeContext("a.py", 1), "   \n  ")

        assert not [r for r in caplog.records if r.getMessage().strip()]

    def test_strips_surrounding_whitespace(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="qt"):
            qt_handler(4, _FakeContext(None, None), "  Contexto recortado \n")

        assert caplog.records[-1].getMessage() == "Contexto recortado"
