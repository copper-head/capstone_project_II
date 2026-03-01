"""Configuration loading for cal-ai.

Reads settings from environment variables (with .env support via python-dotenv)
and validates that all required values are present.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv


def _slugify_owner(name: str) -> str:
    """Convert an owner name to a filesystem-safe slug.

    Lowercase, replace spaces and special characters with underscores,
    collapse consecutive underscores, and strip leading/trailing underscores.

    Examples:
        >>> _slugify_owner("Alice Smith")
        'alice_smith'
        >>> _slugify_owner("Bob's Calendar!")
        'bob_s_calendar'
    """
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables.

    Attributes:
        gemini_api_key: API key for Google Gemini.
        google_account_email: Google account email for calendar access.
        owner_name: Display name of the calendar owner.
        log_level: Logging level (default ``"INFO"``).
        timezone: IANA timezone string (default ``"America/Vancouver"``).
        memory_db_path: Path to the SQLite memory database.  Auto-generated
            from a slugified ``owner_name`` (e.g., ``data/memory_alice_smith.db``)
            unless overridden via the ``MEMORY_DB_PATH`` env var.
    """

    gemini_api_key: str
    google_account_email: str
    owner_name: str
    log_level: str = "INFO"
    timezone: str = "America/Vancouver"
    memory_db_path: str = ""

    def __repr__(self) -> str:
        return (
            f"Settings(gemini_api_key='***', "
            f"google_account_email={self.google_account_email!r}, "
            f"owner_name={self.owner_name!r}, "
            f"log_level={self.log_level!r}, "
            f"timezone={self.timezone!r}, "
            f"memory_db_path={self.memory_db_path!r})"
        )


def load_settings() -> Settings:
    """Load and validate settings from environment variables.

    Calls :func:`dotenv.load_dotenv` so a ``.env`` file in the project root
    is picked up automatically.

    Returns:
        A validated :class:`Settings` instance.

    Raises:
        ConfigError: If any required environment variable is missing,
            empty, or whitespace-only.  The error message names **all**
            missing variables.
    """
    load_dotenv()

    required = {
        "GEMINI_API_KEY": "gemini_api_key",
        "GOOGLE_ACCOUNT_EMAIL": "google_account_email",
        "OWNER_NAME": "owner_name",
    }

    values: dict[str, str] = {}
    missing: list[str] = []

    for env_var, field_name in required.items():
        raw = os.environ.get(env_var, "")
        if not raw.strip():
            missing.append(env_var)
        else:
            values[field_name] = raw

    if missing:
        names = ", ".join(missing)
        raise ConfigError(f"Missing required environment variables: {names}")

    # Optional settings with defaults handled by the dataclass.
    log_level = os.environ.get("LOG_LEVEL", "").strip()
    timezone = os.environ.get("TIMEZONE", "").strip()

    if log_level:
        values["log_level"] = log_level
    if timezone:
        values["timezone"] = timezone

    # Memory DB path: explicit env var overrides auto-generated default.
    memory_db_path = os.environ.get("MEMORY_DB_PATH", "").strip()
    if memory_db_path:
        values["memory_db_path"] = memory_db_path
    else:
        slug = _slugify_owner(values["owner_name"])
        values["memory_db_path"] = f"data/memory_{slug}.db"

    return Settings(**values)
