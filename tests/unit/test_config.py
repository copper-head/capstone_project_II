"""Tests for cal-ai configuration loading."""

from __future__ import annotations

import pytest

from cal_ai.config import ConfigError, _slugify_owner, load_memory_settings, load_settings


class TestLoadSettingsHappyPath:
    """Tests for successful configuration loading."""

    def test_load_settings_with_all_vars_set(
        self, monkeypatch_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All required vars present returns correct Settings."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("TIMEZONE", raising=False)

        settings = load_settings()

        assert settings.gemini_api_key == "test-gemini-key-12345"
        assert settings.google_account_email == "test@example.com"
        assert settings.owner_name == "Test User"

    def test_load_settings_default_log_level(
        self, monkeypatch_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LOG_LEVEL not set defaults to INFO."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        settings = load_settings()

        assert settings.log_level == "INFO"

    def test_load_settings_custom_log_level(
        self, monkeypatch_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LOG_LEVEL=DEBUG is honoured."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        settings = load_settings()

        assert settings.log_level == "DEBUG"

    def test_load_settings_default_timezone(
        self, monkeypatch_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TIMEZONE not set defaults to America/Vancouver."""
        monkeypatch.delenv("TIMEZONE", raising=False)

        settings = load_settings()

        assert settings.timezone == "America/Vancouver"

    def test_load_settings_custom_timezone(
        self, monkeypatch_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TIMEZONE=US/Eastern is honoured."""
        monkeypatch.setenv("TIMEZONE", "US/Eastern")

        settings = load_settings()

        assert settings.timezone == "US/Eastern"


class TestLoadSettingsMissingVars:
    """Tests for missing or invalid environment variables."""

    def test_load_settings_missing_gemini_api_key(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing GEMINI_API_KEY raises ConfigError naming the variable."""
        monkeypatch.setenv("GOOGLE_ACCOUNT_EMAIL", "test@example.com")
        monkeypatch.setenv("OWNER_NAME", "Test User")

        with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
            load_settings()

    def test_load_settings_missing_google_account_email(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing GOOGLE_ACCOUNT_EMAIL raises ConfigError naming the variable."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("OWNER_NAME", "Test User")

        with pytest.raises(ConfigError, match="GOOGLE_ACCOUNT_EMAIL"):
            load_settings()

    def test_load_settings_missing_owner_name(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing OWNER_NAME raises ConfigError naming the variable."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_ACCOUNT_EMAIL", "test@example.com")

        with pytest.raises(ConfigError, match="OWNER_NAME"):
            load_settings()

    def test_load_settings_missing_multiple_vars(self, clean_env: None) -> None:
        """Multiple missing vars raises ConfigError naming ALL of them."""
        with pytest.raises(ConfigError) as exc_info:
            load_settings()

        message = str(exc_info.value)
        assert "GEMINI_API_KEY" in message
        assert "GOOGLE_ACCOUNT_EMAIL" in message
        assert "OWNER_NAME" in message

    def test_load_settings_empty_string_gemini_key(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty GEMINI_API_KEY raises ConfigError."""
        monkeypatch.setenv("GEMINI_API_KEY", "")
        monkeypatch.setenv("GOOGLE_ACCOUNT_EMAIL", "test@example.com")
        monkeypatch.setenv("OWNER_NAME", "Test User")

        with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
            load_settings()

    def test_load_settings_empty_string_email(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty GOOGLE_ACCOUNT_EMAIL raises ConfigError."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_ACCOUNT_EMAIL", "")
        monkeypatch.setenv("OWNER_NAME", "Test User")

        with pytest.raises(ConfigError, match="GOOGLE_ACCOUNT_EMAIL"):
            load_settings()

    def test_load_settings_empty_string_owner(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty OWNER_NAME raises ConfigError."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_ACCOUNT_EMAIL", "test@example.com")
        monkeypatch.setenv("OWNER_NAME", "")

        with pytest.raises(ConfigError, match="OWNER_NAME"):
            load_settings()

    def test_load_settings_whitespace_only_value(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Whitespace-only OWNER_NAME raises ConfigError."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_ACCOUNT_EMAIL", "test@example.com")
        monkeypatch.setenv("OWNER_NAME", "   ")

        with pytest.raises(ConfigError, match="OWNER_NAME"):
            load_settings()


class TestSettingsDataclass:
    """Tests for the Settings dataclass behaviour."""

    def test_settings_repr_masks_api_key(self, monkeypatch_env: dict[str, str]) -> None:
        """repr(settings) must NOT leak the actual API key."""
        settings = load_settings()
        text = repr(settings)

        assert "test-gemini-key-12345" not in text
        assert "***" in text

    def test_settings_repr_shows_email(self, monkeypatch_env: dict[str, str]) -> None:
        """repr(settings) includes the email value."""
        settings = load_settings()
        text = repr(settings)

        assert "test@example.com" in text

    def test_settings_repr_shows_owner(self, monkeypatch_env: dict[str, str]) -> None:
        """repr(settings) includes the owner name."""
        settings = load_settings()
        text = repr(settings)

        assert "Test User" in text

    def test_settings_is_frozen(self, monkeypatch_env: dict[str, str]) -> None:
        """Mutating a field on a frozen dataclass must raise."""
        settings = load_settings()

        with pytest.raises(AttributeError):
            settings.owner_name = "Changed"  # type: ignore[misc]


class TestConfigError:
    """Tests for the ConfigError exception class."""

    def test_config_error_is_exception(self) -> None:
        """ConfigError must be a subclass of Exception."""
        assert issubclass(ConfigError, Exception)

    def test_config_error_message(self) -> None:
        """ConfigError preserves the message string."""
        error = ConfigError("something went wrong")

        assert str(error) == "something went wrong"


class TestSlugifyOwner:
    """Tests for the _slugify_owner helper."""

    def test_simple_name(self) -> None:
        """Simple two-word name produces lowercase underscore slug."""
        assert _slugify_owner("Alice Smith") == "alice_smith"

    def test_special_characters(self) -> None:
        """Special characters are replaced with underscores."""
        assert _slugify_owner("Bob's Calendar!") == "bob_s_calendar"

    def test_consecutive_specials_collapsed(self) -> None:
        """Multiple consecutive special chars collapse to one underscore."""
        assert _slugify_owner("Alice---Smith") == "alice_smith"

    def test_leading_trailing_stripped(self) -> None:
        """Leading/trailing underscores are stripped."""
        assert _slugify_owner("  Alice  ") == "alice"

    def test_empty_slug_raises(self) -> None:
        """All non-ASCII name produces empty slug and raises ConfigError."""
        with pytest.raises(ConfigError, match="empty slug"):
            _slugify_owner("日本語")

    def test_emoji_only_raises(self) -> None:
        """Emoji-only name produces empty slug and raises ConfigError."""
        with pytest.raises(ConfigError, match="empty slug"):
            _slugify_owner("🎉🎊")


class TestLoadMemorySettings:
    """Tests for load_memory_settings (lightweight memory-only config)."""

    def test_returns_path_from_owner_name(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With only OWNER_NAME set, returns auto-generated path."""
        monkeypatch.setenv("OWNER_NAME", "Alice Smith")

        result = load_memory_settings()

        assert result == "data/memory_alice_smith.db"

    def test_does_not_require_api_keys(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Does not raise when GEMINI_API_KEY and GOOGLE_ACCOUNT_EMAIL are missing."""
        monkeypatch.setenv("OWNER_NAME", "Alice")

        result = load_memory_settings()

        assert result == "data/memory_alice.db"

    def test_memory_db_path_override(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MEMORY_DB_PATH env var overrides auto-generated path."""
        monkeypatch.setenv("MEMORY_DB_PATH", "/tmp/custom.db")

        result = load_memory_settings()

        assert result == "/tmp/custom.db"

    def test_memory_db_path_override_without_owner(
        self, clean_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MEMORY_DB_PATH works even without OWNER_NAME."""
        monkeypatch.setenv("MEMORY_DB_PATH", "/tmp/custom.db")

        result = load_memory_settings()

        assert result == "/tmp/custom.db"

    def test_missing_owner_and_path_raises(self, clean_env: None) -> None:
        """Missing both OWNER_NAME and MEMORY_DB_PATH raises ConfigError."""
        with pytest.raises(ConfigError, match="OWNER_NAME"):
            load_memory_settings()

    def test_empty_owner_raises(self, clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        """Whitespace-only OWNER_NAME without MEMORY_DB_PATH raises ConfigError."""
        monkeypatch.setenv("OWNER_NAME", "   ")

        with pytest.raises(ConfigError, match="OWNER_NAME"):
            load_memory_settings()
