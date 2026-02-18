"""Tests for Google Calendar OAuth 2.0 authentication.

Covers the ``get_calendar_credentials`` function which implements a three-step
authentication strategy: cached token, token refresh, and browser OAuth flow.

Test matrix (7 tests):

| Test | Scenario | Expected |
|---|---|---|
| test_load_cached_token_valid | token.json valid | Returns cached creds, no flow |
| test_expired_token_triggers_refresh | Token expired, refresh OK | refresh() called, token saved |
| test_refresh_failure_triggers_reauth | Refresh fails | Falls back to browser flow |
| test_no_cached_token_launches_browser_flow | No token.json | InstalledAppFlow launched |
| test_missing_credentials_json_raises_error | No credentials.json | CalendarAuthError |
| test_token_saved_after_successful_auth | After browser auth | token.json written |
| test_correct_scopes_requested | OAuth flow scopes | Scope is calendar |
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, create_autospec, patch

import pytest
from google.oauth2.credentials import Credentials

from cal_ai.calendar.auth import SCOPES, get_calendar_credentials
from cal_ai.calendar.exceptions import CalendarAuthError


class TestLoadCachedTokenValid:
    """Cached token exists and is still valid -- no browser flow needed."""

    def test_load_cached_token_valid(
        self, tmp_path: Path, mock_credentials: MagicMock
    ) -> None:
        """Valid cached token is returned directly without launching a browser flow."""
        token_path = tmp_path / "token.json"
        token_path.write_text('{"token": "cached"}')
        creds_path = tmp_path / "credentials.json"
        creds_path.write_text('{"installed": {}}')

        with patch(
            "cal_ai.calendar.auth._load_cached_token",
            return_value=mock_credentials,
        ) as mock_load, patch(
            "cal_ai.calendar.auth._run_browser_flow",
        ) as mock_flow:
            result = get_calendar_credentials(creds_path, token_path)

        mock_load.assert_called_once_with(token_path)
        mock_flow.assert_not_called()
        assert result is mock_credentials


class TestExpiredTokenRefresh:
    """Token is expired but has a refresh token -- refresh should be attempted."""

    def test_expired_token_triggers_refresh(
        self, tmp_path: Path, mock_expired_credentials: MagicMock
    ) -> None:
        """Expired token with a refresh token triggers creds.refresh() and saves."""
        token_path = tmp_path / "token.json"
        token_path.write_text('{"token": "expired"}')
        creds_path = tmp_path / "credentials.json"
        creds_path.write_text('{"installed": {}}')

        # After refresh, mark the credentials as valid.
        refreshed_creds = mock_expired_credentials

        with patch(
            "cal_ai.calendar.auth._load_cached_token",
            return_value=mock_expired_credentials,
        ), patch(
            "cal_ai.calendar.auth._refresh_token",
            return_value=refreshed_creds,
        ) as mock_refresh, patch(
            "cal_ai.calendar.auth._save_token",
        ) as mock_save:
            result = get_calendar_credentials(creds_path, token_path)

        mock_refresh.assert_called_once_with(mock_expired_credentials)
        mock_save.assert_called_once_with(refreshed_creds, token_path)
        assert result is refreshed_creds

    def test_refresh_failure_triggers_reauth(
        self, tmp_path: Path, mock_expired_credentials: MagicMock
    ) -> None:
        """When token refresh fails, browser OAuth flow is launched as fallback."""
        token_path = tmp_path / "token.json"
        creds_path = tmp_path / "credentials.json"
        creds_path.write_text('{"installed": {}}')

        fresh_creds = create_autospec(Credentials, instance=True)
        fresh_creds.valid = True
        fresh_creds.to_json.return_value = '{"token": "new"}'

        with patch(
            "cal_ai.calendar.auth._load_cached_token",
            return_value=mock_expired_credentials,
        ), patch(
            "cal_ai.calendar.auth._refresh_token",
            return_value=None,
        ), patch(
            "cal_ai.calendar.auth._run_browser_flow",
            return_value=fresh_creds,
        ) as mock_flow, patch(
            "cal_ai.calendar.auth._save_token",
        ) as mock_save:
            result = get_calendar_credentials(creds_path, token_path)

        mock_flow.assert_called_once_with(creds_path)
        mock_save.assert_called_once_with(fresh_creds, token_path)
        assert result is fresh_creds


class TestNoCachedToken:
    """No cached token exists -- browser flow must be launched."""

    def test_no_cached_token_launches_browser_flow(self, tmp_path: Path) -> None:
        """When no token.json exists, the browser OAuth flow is launched."""
        token_path = tmp_path / "token.json"
        # token_path does NOT exist
        creds_path = tmp_path / "credentials.json"
        creds_path.write_text('{"installed": {}}')

        fresh_creds = create_autospec(Credentials, instance=True)
        fresh_creds.valid = True
        fresh_creds.to_json.return_value = '{"token": "new"}'

        with patch(
            "cal_ai.calendar.auth._load_cached_token",
            return_value=None,
        ), patch(
            "cal_ai.calendar.auth._run_browser_flow",
            return_value=fresh_creds,
        ) as mock_flow, patch(
            "cal_ai.calendar.auth._save_token",
        ) as mock_save:
            result = get_calendar_credentials(creds_path, token_path)

        mock_flow.assert_called_once_with(creds_path)
        mock_save.assert_called_once_with(fresh_creds, token_path)
        assert result is fresh_creds


class TestMissingCredentialsFile:
    """credentials.json does not exist -- CalendarAuthError expected."""

    def test_missing_credentials_json_raises_error(self, tmp_path: Path) -> None:
        """Missing credentials.json raises CalendarAuthError."""
        token_path = tmp_path / "token.json"
        creds_path = tmp_path / "credentials.json"
        # creds_path does NOT exist

        with patch(
            "cal_ai.calendar.auth._load_cached_token",
            return_value=None,
        ), pytest.raises(CalendarAuthError, match="client secrets"):
            get_calendar_credentials(creds_path, token_path)


class TestTokenSavedAfterAuth:
    """After a successful browser auth, the token must be persisted."""

    def test_token_saved_after_successful_auth(self, tmp_path: Path) -> None:
        """Token is saved to disk after a successful browser OAuth flow."""
        token_path = tmp_path / "token.json"
        creds_path = tmp_path / "credentials.json"
        creds_path.write_text('{"installed": {}}')

        fresh_creds = create_autospec(Credentials, instance=True)
        fresh_creds.valid = True
        fresh_creds.to_json.return_value = '{"token": "brand-new"}'

        with patch(
            "cal_ai.calendar.auth._load_cached_token",
            return_value=None,
        ), patch(
            "cal_ai.calendar.auth._run_browser_flow",
            return_value=fresh_creds,
        ), patch(
            "cal_ai.calendar.auth._save_token",
        ) as mock_save:
            get_calendar_credentials(creds_path, token_path)

        mock_save.assert_called_once_with(fresh_creds, token_path)


class TestCorrectScopesRequested:
    """The OAuth flow must request the correct Calendar scope."""

    def test_correct_scopes_requested(self, tmp_path: Path) -> None:
        """InstalledAppFlow is invoked with the Calendar scope."""
        creds_path = tmp_path / "credentials.json"
        creds_path.write_text(
            '{"installed": {"client_id": "fake", "client_secret": "fake",'
            ' "auth_uri": "https://accounts.google.com/o/oauth2/auth",'
            ' "token_uri": "https://oauth2.googleapis.com/token"}}'
        )

        mock_creds = create_autospec(Credentials, instance=True)
        mock_creds.valid = True
        mock_creds.to_json.return_value = '{"token": "test"}'

        mock_flow_instance = MagicMock()
        mock_flow_instance.run_local_server.return_value = mock_creds

        with patch(
            "cal_ai.calendar.auth._load_cached_token",
            return_value=None,
        ), patch(
            "cal_ai.calendar.auth.InstalledAppFlow.from_client_secrets_file",
            return_value=mock_flow_instance,
        ) as mock_from_secrets, patch(
            "cal_ai.calendar.auth._save_token",
        ):
            from cal_ai.calendar.auth import _run_browser_flow

            result = _run_browser_flow(creds_path)

        mock_from_secrets.assert_called_once_with(
            str(creds_path),
            scopes=SCOPES,
        )
        assert "https://www.googleapis.com/auth/calendar" in SCOPES
        assert result is mock_creds
