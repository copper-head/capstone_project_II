"""Shared fixtures for cal-ai tests."""

from __future__ import annotations

import logging
from collections.abc import Generator

import pytest


@pytest.fixture()
def monkeypatch_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set all required environment variables to valid defaults.

    Also patches ``load_dotenv`` so that a real ``.env`` file on disk does not
    override the test values.

    Returns the dict of variables so tests can inspect or override values.
    """
    monkeypatch.setattr("cal_ai.config.load_dotenv", lambda *_a, **_kw: None)
    env_vars = {
        "GEMINI_API_KEY": "test-gemini-key-12345",
        "GOOGLE_ACCOUNT_EMAIL": "test@example.com",
        "OWNER_NAME": "Test User",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    return env_vars


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all cal-ai-related environment variables.

    Patches ``load_dotenv`` so a real ``.env`` file cannot re-inject values
    that the test explicitly removed.
    """
    monkeypatch.setattr("cal_ai.config.load_dotenv", lambda *_a, **_kw: None)
    for key in (
        "GEMINI_API_KEY",
        "GOOGLE_ACCOUNT_EMAIL",
        "OWNER_NAME",
        "LOG_LEVEL",
        "TIMEZONE",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _reset_root_logger() -> Generator[None, None, None]:
    """Reset the root logger after each test to prevent handler leaks."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    yield
    root.handlers = original_handlers
    root.setLevel(original_level)
