"""Unit tests for the web application factory, health endpoint, and page routes.

Tests cover: health endpoint response, static files mount, Jinja2 template
configuration, config warning check when GEMINI_API_KEY is missing, page routes
(GET /, GET /memory) returning 200 with correct content, and config warning
rendering in page templates.
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


class TestIndexPage:
    """Tests for the ``GET /`` pipeline page route."""

    def test_index_returns_200(self) -> None:
        """GET / returns 200 status code."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/")

        assert response.status_code == 200

    def test_index_returns_html(self) -> None:
        """GET / returns content-type text/html."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/")

        assert "text/html" in response.headers["content-type"]

    def test_index_contains_split_view(self) -> None:
        """GET / response contains split-view layout structure."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/")
        html = response.text

        assert "split-view" in html
        assert "split-view__left" in html
        assert "split-view__right" in html

    def test_index_contains_nav_bar(self) -> None:
        """GET / response contains the nav bar with Cal-AI text and page links."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/")
        html = response.text

        assert "Cal-AI" in html
        assert 'href="/"' in html
        assert 'href="/memory"' in html

    def test_index_contains_stage_tracker(self) -> None:
        """GET / response contains all 6 stage tracker items."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/")
        html = response.text

        assert "Parsing Transcript" in html
        assert "Loading Memories" in html
        assert "Fetching Calendar" in html
        assert "Extracting Events (LLM)" in html
        assert "Syncing Calendar" in html
        assert "Updating Memory" in html

    def test_index_contains_input_tabs(self) -> None:
        """GET / response contains upload and paste input tabs."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/")
        html = response.text

        assert "Upload File" in html
        assert "Paste Text" in html
        assert "drop-zone" in html
        assert "transcript-textarea" in html

    def test_index_contains_dry_run_checkbox(self) -> None:
        """GET / response contains dry-run checkbox."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/")
        html = response.text

        assert "dry-run-checkbox" in html
        assert "Dry run" in html

    def test_index_contains_submit_button(self) -> None:
        """GET / response contains submit button."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/")
        html = response.text

        assert "submit-btn" in html
        assert "Run Pipeline" in html

    def test_index_contains_terminal_output(self) -> None:
        """GET / response contains terminal output block."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/")
        html = response.text

        assert "terminal-output" in html

    def test_index_contains_log_viewer(self) -> None:
        """GET / response contains expandable log viewer."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/")
        html = response.text

        assert "log-viewer" in html
        assert "Raw Pipeline Logs" in html


class TestMemoryPage:
    """Tests for the ``GET /memory`` memory viewer page route."""

    def test_memory_returns_200(self) -> None:
        """GET /memory returns 200 status code."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/memory")

        assert response.status_code == 200

    def test_memory_returns_html(self) -> None:
        """GET /memory returns content-type text/html."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/memory")

        assert "text/html" in response.headers["content-type"]

    def test_memory_contains_viewer(self) -> None:
        """GET /memory response contains memory viewer structure."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/memory")
        html = response.text

        assert "memory-container" in html
        assert "Memory Viewer" in html

    def test_memory_contains_nav_bar(self) -> None:
        """GET /memory response contains the nav bar with Cal-AI text."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/memory")
        html = response.text

        assert "Cal-AI" in html
        assert 'href="/"' in html
        assert 'href="/memory"' in html

    def test_memory_contains_empty_state(self) -> None:
        """GET /memory response contains instructional empty state message."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/memory")
        html = response.text

        assert "No memories yet" in html
        assert "Run a pipeline to start building memory" in html


class TestConfigWarningRendering:
    """Tests for config warning banner rendering in page templates."""

    def test_index_shows_warning_when_gemini_key_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET / renders warning banner when GEMINI_API_KEY is missing."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with patch("cal_ai.web.app.load_dotenv"):
            app = create_app()
        client = TestClient(app)

        response = client.get("/")
        html = response.text

        assert "config-warning-banner" in html
        assert "GEMINI_API_KEY" in html

    def test_memory_shows_warning_when_gemini_key_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET /memory renders warning banner when GEMINI_API_KEY is missing."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with patch("cal_ai.web.app.load_dotenv"):
            app = create_app()
        client = TestClient(app)

        response = client.get("/memory")
        html = response.text

        assert "config-warning-banner" in html
        assert "GEMINI_API_KEY" in html

    def test_index_no_warning_when_gemini_key_present(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET / does not render warning banner when GEMINI_API_KEY is set."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-12345")
        with patch("cal_ai.web.app.load_dotenv"):
            app = create_app()
        client = TestClient(app)

        response = client.get("/")
        html = response.text

        assert "config-warning-banner" not in html
