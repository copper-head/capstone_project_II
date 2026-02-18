"""OAuth 2.0 authentication for Google Calendar API.

Implements the Desktop application OAuth flow using Google's
``google-auth-oauthlib`` library.  Handles token caching, refresh,
and re-authentication when credentials expire or are missing.

Usage::

    from cal_ai.calendar.auth import get_calendar_credentials

    creds = get_calendar_credentials(
        credentials_path=Path("credentials.json"),
        token_path=Path("token.json"),
    )
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from cal_ai.calendar.exceptions import CalendarAuthError

logger = logging.getLogger(__name__)

SCOPES: list[str] = ["https://www.googleapis.com/auth/calendar"]
"""OAuth 2.0 scopes required for full Calendar CRUD access."""


def get_calendar_credentials(
    credentials_path: Path | str,
    token_path: Path | str,
) -> Credentials:
    """Obtain valid Google Calendar OAuth 2.0 credentials.

    Follows a three-step strategy:

    1. **Cached token** -- load ``token_path`` and return if still valid.
    2. **Refresh** -- if the cached token is expired but has a refresh token,
       attempt to refresh it.  On success, save the updated token and return.
    3. **Browser flow** -- if no cached token exists, or refresh fails,
       launch the ``InstalledAppFlow`` local-server OAuth flow to obtain
       new credentials.

    Every step is logged at INFO level for demo observability.

    Args:
        credentials_path: Path to the OAuth client secrets file
            (``credentials.json``) downloaded from Google Cloud Console.
        token_path: Path where the cached user token is stored
            (``token.json``).  Created/updated automatically.

    Returns:
        A valid :class:`google.oauth2.credentials.Credentials` instance
        with the ``calendar`` scope.

    Raises:
        CalendarAuthError: If ``credentials_path`` does not exist (cannot
            start OAuth flow) or if all authentication strategies fail.
    """
    credentials_path = Path(credentials_path)
    token_path = Path(token_path)

    # Step 1: Try loading a cached token.
    creds = _load_cached_token(token_path)

    if creds is not None and creds.valid:
        logger.info("Loaded valid cached token from %s", token_path)
        return creds

    # Step 2: Try refreshing an expired token.
    if creds is not None and creds.expired and creds.refresh_token:
        logger.info("Cached token expired, attempting refresh")
        refreshed = _refresh_token(creds)
        if refreshed is not None:
            _save_token(refreshed, token_path)
            logger.info("Token refreshed and saved to %s", token_path)
            return refreshed
        logger.warning("Token refresh failed, falling back to browser flow")

    # Step 3: Run the full browser-based OAuth flow.
    logger.info("Starting browser-based OAuth flow")
    creds = _run_browser_flow(credentials_path)
    _save_token(creds, token_path)
    logger.info("New credentials obtained and saved to %s", token_path)
    return creds


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_cached_token(token_path: Path) -> Credentials | None:
    """Load credentials from a cached token file.

    Args:
        token_path: Path to the cached ``token.json`` file.

    Returns:
        A :class:`Credentials` instance, or ``None`` if the file does not
        exist or cannot be parsed.
    """
    if not token_path.exists():
        logger.info("No cached token found at %s", token_path)
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        logger.info("Cached token loaded from %s", token_path)
        return creds
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        logger.warning("Failed to parse cached token at %s: %s", token_path, exc)
        return None


def _refresh_token(creds: Credentials) -> Credentials | None:
    """Attempt to refresh expired credentials.

    Args:
        creds: Expired credentials with a valid refresh token.

    Returns:
        The refreshed :class:`Credentials` instance, or ``None`` if the
        refresh request fails.
    """
    try:
        creds.refresh(Request())
        logger.info("Token refresh succeeded")
        return creds
    except Exception as exc:
        logger.warning("Token refresh failed: %s", exc)
        return None


def _run_browser_flow(credentials_path: Path) -> Credentials:
    """Launch the InstalledAppFlow to authenticate via browser.

    Args:
        credentials_path: Path to the OAuth client secrets JSON file.

    Returns:
        Fresh :class:`Credentials` from the completed OAuth flow.

    Raises:
        CalendarAuthError: If the client secrets file is missing.
    """
    if not credentials_path.exists():
        msg = f"OAuth client secrets file not found: {credentials_path}"
        logger.error(msg)
        raise CalendarAuthError(msg)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_path),
        scopes=SCOPES,
    )
    creds = flow.run_local_server(port=0)
    logger.info("Browser OAuth flow completed successfully")
    return creds


def _save_token(creds: Credentials, token_path: Path) -> None:
    """Persist credentials to a token file.

    Creates parent directories if they do not exist.

    Args:
        creds: The credentials to save.
        token_path: Destination path for the token JSON file.
    """
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    logger.info("Token saved to %s", token_path)
