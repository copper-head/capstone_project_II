"""Unit tests for the web application factory and health endpoint.

Tests cover: health endpoint response, static files mount, Jinja2 template
configuration, and config warning check when GEMINI_API_KEY is missing.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from cal_ai.web.app import create_app


class TestHealthEndpoint:
    """Tests for the ``GET /api/health`` endpoint."""

    def test_health_returns_ok(self) -> None:
        """GET /api/health returns 200 with {"status": "ok"}."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/api/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestStaticFilesMount:
    """Tests for static file serving configuration."""

    def test_static_mount_exists(self) -> None:
        """The app has a route mounted at /static."""
        app = create_app()
        route_paths = [route.path for route in app.routes]
        assert "/static" in route_paths or any(
            getattr(route, "path", "").startswith("/static") for route in app.routes
        )


class TestTemplateConfig:
    """Tests for Jinja2 template configuration."""

    def test_templates_stored_on_app_state(self) -> None:
        """create_app() stores Jinja2Templates on app.state.templates."""
        app = create_app()
        assert hasattr(app.state, "templates")
        assert app.state.templates is not None


class TestConfigWarningCheck:
    """Tests for config warning detection on startup."""

    def test_missing_gemini_key_adds_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When GEMINI_API_KEY is not set, config_warnings contains a warning."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with patch("cal_ai.web.app.load_dotenv"):
            app = create_app()

        assert len(app.state.config_warnings) >= 1
        assert any("GEMINI_API_KEY" in w for w in app.state.config_warnings)

    def test_present_gemini_key_no_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When GEMINI_API_KEY is set, config_warnings is empty."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-12345")
        with patch("cal_ai.web.app.load_dotenv"):
            app = create_app()

        assert app.state.config_warnings == []
