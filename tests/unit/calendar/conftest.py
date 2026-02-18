"""Shared fixtures for Google Calendar unit tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, create_autospec

import pytest
from google.oauth2.credentials import Credentials

from cal_ai.calendar.auth import SCOPES


@pytest.fixture()
def mock_credentials() -> MagicMock:
    """Return a mock Credentials object that reports as valid."""
    creds = create_autospec(Credentials, instance=True)
    creds.valid = True
    creds.expired = False
    creds.refresh_token = "fake-refresh-token"
    creds.to_json.return_value = '{"token": "fake"}'
    return creds


@pytest.fixture()
def mock_expired_credentials() -> MagicMock:
    """Return a mock Credentials object that is expired but has a refresh token."""
    creds = create_autospec(Credentials, instance=True)
    creds.valid = False
    creds.expired = True
    creds.refresh_token = "fake-refresh-token"
    creds.to_json.return_value = '{"token": "refreshed"}'
    return creds


@pytest.fixture()
def tmp_credentials_file(tmp_path: Path) -> Path:
    """Write a minimal credentials.json to a temp directory and return its path."""
    creds_path = tmp_path / "credentials.json"
    creds_path.write_text('{"installed": {"client_id": "fake", "client_secret": "fake"}}')
    return creds_path


@pytest.fixture()
def tmp_token_file(tmp_path: Path) -> Path:
    """Return a path for token.json in a temp directory (file does not exist yet)."""
    return tmp_path / "token.json"


@pytest.fixture()
def scopes() -> list[str]:
    """Return the expected OAuth 2.0 scopes."""
    return SCOPES
