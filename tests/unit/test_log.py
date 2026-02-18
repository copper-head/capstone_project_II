"""Tests for cal-ai structured logging."""

from __future__ import annotations

import logging
import re

import pytest

from cal_ai.log import get_logger, setup_logging


class TestSetupLogging:
    """Tests for the setup_logging function."""

    def test_setup_logging_does_not_raise(self) -> None:
        """Calling setup_logging() must not raise."""
        setup_logging()

    def test_setup_logging_sets_level(self) -> None:
        """setup_logging('DEBUG') must set root logger to DEBUG."""
        setup_logging("DEBUG")

        assert logging.getLogger().level == logging.DEBUG

    def test_setup_logging_default_level_is_info(self) -> None:
        """setup_logging() with no args defaults to INFO."""
        setup_logging()

        assert logging.getLogger().level == logging.INFO

    def test_setup_logging_invalid_level_raises(self) -> None:
        """An unrecognised level string must raise ValueError."""
        with pytest.raises(ValueError, match="Invalid log level"):
            setup_logging("INVALID")

    def test_setup_logging_adds_handler(self) -> None:
        """After setup_logging() the root logger must have a StreamHandler."""
        setup_logging()

        root = logging.getLogger()
        stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream_handlers) >= 1

    def test_setup_logging_idempotent(self) -> None:
        """Calling setup_logging() twice must not add duplicate handlers."""
        setup_logging()
        count_after_first = len(logging.getLogger().handlers)

        setup_logging()
        count_after_second = len(logging.getLogger().handlers)

        assert count_after_second == count_after_first


class TestGetLogger:
    """Tests for the get_logger function."""

    def test_get_logger_returns_logger(self) -> None:
        """get_logger() must return a logging.Logger instance."""
        logger = get_logger("test")

        assert isinstance(logger, logging.Logger)

    def test_get_logger_name(self) -> None:
        """get_logger() must return a logger with the requested name."""
        logger = get_logger("cal_ai.test")

        assert logger.name == "cal_ai.test"


class TestLogOutput:
    """Tests for the actual log output format."""

    def test_log_output_contains_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Log output must contain the level name."""
        setup_logging("INFO")
        logger = get_logger("test.level")
        logger.info("check level")

        captured = capsys.readouterr()
        assert "INFO" in captured.err

    def test_log_output_contains_logger_name(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Log output must contain the logger name."""
        setup_logging("INFO")
        logger = get_logger("test.name_check")
        logger.info("check name")

        captured = capsys.readouterr()
        assert "test.name_check" in captured.err

    def test_log_output_contains_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Log output must contain the message text."""
        setup_logging("INFO")
        logger = get_logger("test.msg")
        logger.info("hello world")

        captured = capsys.readouterr()
        assert "hello world" in captured.err

    def test_log_output_contains_timestamp(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Log output must contain an ISO 8601 timestamp."""
        setup_logging("INFO")
        logger = get_logger("test.timestamp")
        logger.info("timestamp check")

        captured = capsys.readouterr()
        # Match ISO 8601 date-time pattern: YYYY-MM-DDTHH:MM:SS
        assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", captured.err)

    def test_log_output_has_pipe_separators(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Log output must use pipe characters as field separators."""
        setup_logging("INFO")
        logger = get_logger("test.pipes")
        logger.info("pipe check")

        captured = capsys.readouterr()
        assert " | " in captured.err

    def test_debug_not_shown_at_info_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        """DEBUG messages must not appear when level is INFO."""
        setup_logging("INFO")
        logger = get_logger("test.filter")
        logger.debug("should not appear")

        captured = capsys.readouterr()
        assert "should not appear" not in captured.err

    def test_debug_shown_at_debug_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        """DEBUG messages must appear when level is DEBUG."""
        setup_logging("DEBUG")
        logger = get_logger("test.debug_show")
        logger.debug("should appear")

        captured = capsys.readouterr()
        assert "should appear" in captured.err
