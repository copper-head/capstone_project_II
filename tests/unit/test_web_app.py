"""Unit tests for the web application factory, health endpoint, page routes,
pipeline SSE endpoint, and memory API endpoint.

Tests cover: health endpoint response, static files mount, Jinja2 template
configuration, config warning check when GEMINI_API_KEY is missing, page routes
(GET /, GET /memory) returning 200 with correct content, config warning
rendering in page templates, pipeline SSE mock test with log capture, memory
endpoint test, and log event test.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

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
        from cal_ai.config import ConfigError

        with (
            patch("cal_ai.web.app.load_dotenv"),
            patch(
                "cal_ai.web.routes.load_memory_settings",
                side_effect=ConfigError("no config"),
            ),
        ):
            app = create_app()
            client = TestClient(app)

            response = client.get("/memory")
            html = response.text

        assert "No memories yet" in html
        assert "Run a pipeline to start building memory" in html

    def test_memory_renders_accordion_with_entries(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """GET /memory renders server-side accordion sections with entries."""
        from cal_ai.memory.store import MemoryStore

        db_path = tmp_path / "test_memory.db"
        store = MemoryStore(str(db_path))
        store.upsert("preferences", "coffee", "likes lattes", "high")
        store.upsert("people", "bob", "prefers mornings", "medium")
        store.close()

        monkeypatch.setenv("MEMORY_DB_PATH", str(db_path))

        with patch("cal_ai.web.app.load_dotenv"):
            app = create_app()
        client = TestClient(app)

        response = client.get("/memory")
        html = response.text

        # Accordion sections rendered server-side.
        assert "memory-category" in html
        assert "memory-entry" in html
        # Entry content rendered.
        assert "coffee" in html
        assert "likes lattes" in html
        assert "badge-confidence--high" in html
        assert "bob" in html
        assert "prefers mornings" in html
        assert "badge-confidence--medium" in html
        # Empty state NOT shown.
        assert "No memories yet" not in html


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


# ---------------------------------------------------------------------------
# Pipeline SSE endpoint tests
# ---------------------------------------------------------------------------


def _make_mock_pipeline_result():
    """Create a mock PipelineResult for SSE testing."""
    from cal_ai.models.extraction import ExtractedEvent
    from cal_ai.pipeline import EventSyncResult, PipelineResult

    event = ExtractedEvent(
        title="Test Meeting",
        start_time="2026-03-05T10:00:00",
        end_time="2026-03-05T11:00:00",
        confidence="high",
        reasoning="Explicitly mentioned.",
        action="create",
    )
    sync = EventSyncResult(
        event=event,
        action_taken="would_create",
        success=True,
    )
    return PipelineResult(
        transcript_path=Path("/tmp/test.txt"),
        speakers_found=["Alice", "Bob"],
        utterance_count=3,
        events_extracted=[event],
        events_synced=[sync],
        duration_seconds=1.5,
        dry_run=True,
    )


def _run_mock_pipeline(transcript_path, owner, dry_run=False):
    """Mock run_pipeline that emits actual log line patterns."""
    pipeline_logger = logging.getLogger("cal_ai.pipeline")

    pipeline_logger.info("Stage 1: Loading and parsing transcript from %s", transcript_path)
    pipeline_logger.info("Stage 1 complete: 2 speaker(s), 3 utterance(s)")
    pipeline_logger.info("Memory context loaded: 2 memorie(s)")
    pipeline_logger.info("Calendar context fetched: 5 event(s) in window")
    pipeline_logger.info("Stage 2: Extracting events via LLM")
    pipeline_logger.info("Stage 2 complete: 1 event(s) extracted")
    pipeline_logger.info("Stage 3: Dry-run mode -- skipping calendar sync")
    pipeline_logger.info("Stage 4: Dry-run mode -- skipping memory write")

    return _make_mock_pipeline_result()


class TestPipelineSSE:
    """Tests for the ``POST /api/pipeline/run`` SSE endpoint."""

    def test_pipeline_with_text_returns_sse_stream(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/pipeline/run with text returns SSE stream with events."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_ACCOUNT_EMAIL", "test@example.com")
        monkeypatch.setenv("OWNER_NAME", "TestOwner")

        with (
            patch("cal_ai.web.app.load_dotenv"),
            patch("cal_ai.web.routes.load_settings") as mock_settings,
        ):
            settings_mock = MagicMock()
            settings_mock.owner_name = "TestOwner"
            mock_settings.return_value = settings_mock

            app = create_app()
            client = TestClient(app)

            with (
                patch(
                    "cal_ai.web.routes.run_pipeline",
                    side_effect=_run_mock_pipeline,
                ),
                client.stream(
                    "POST",
                    "/api/pipeline/run",
                    data={"text": "[Alice]: Let's meet tomorrow at 10am."},
                ) as response,
            ):
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")

                body = response.read().decode("utf-8")

        # Parse SSE events.
        events = _parse_sse_events(body)
        event_types = [e["type"] for e in events]

        # Must have stage, log, result, and done events.
        assert "stage" in event_types
        assert "log" in event_types
        assert "result" in event_types
        assert "done" in event_types

    def test_pipeline_with_file_returns_sse_stream(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/pipeline/run with file upload returns SSE stream."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_ACCOUNT_EMAIL", "test@example.com")
        monkeypatch.setenv("OWNER_NAME", "TestOwner")

        with (
            patch("cal_ai.web.app.load_dotenv"),
            patch("cal_ai.web.routes.load_settings") as mock_settings,
        ):
            settings_mock = MagicMock()
            settings_mock.owner_name = "TestOwner"
            mock_settings.return_value = settings_mock

            app = create_app()
            client = TestClient(app)

            with (
                patch(
                    "cal_ai.web.routes.run_pipeline",
                    side_effect=_run_mock_pipeline,
                ),
                client.stream(
                    "POST",
                    "/api/pipeline/run",
                    files={"file": ("test.txt", b"[Alice]: Let's meet tomorrow.", "text/plain")},
                ) as response,
            ):
                assert response.status_code == 200
                body = response.read().decode("utf-8")

        events = _parse_sse_events(body)
        event_types = [e["type"] for e in events]
        assert "result" in event_types
        assert "done" in event_types

    def test_pipeline_no_input_returns_422(self) -> None:
        """POST /api/pipeline/run with no file or text returns 422."""
        app = create_app()
        client = TestClient(app)

        response = client.post("/api/pipeline/run")

        assert response.status_code == 422

    def test_pipeline_sse_includes_log_events(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """SSE stream includes event:log events with message, level, and logger."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_ACCOUNT_EMAIL", "test@example.com")
        monkeypatch.setenv("OWNER_NAME", "TestOwner")

        with (
            patch("cal_ai.web.app.load_dotenv"),
            patch("cal_ai.web.routes.load_settings") as mock_settings,
        ):
            settings_mock = MagicMock()
            settings_mock.owner_name = "TestOwner"
            mock_settings.return_value = settings_mock

            app = create_app()
            client = TestClient(app)

            with (
                patch(
                    "cal_ai.web.routes.run_pipeline",
                    side_effect=_run_mock_pipeline,
                ),
                client.stream(
                    "POST",
                    "/api/pipeline/run",
                    data={"text": "[Alice]: Meeting tomorrow."},
                ) as response,
            ):
                body = response.read().decode("utf-8")

        events = _parse_sse_events(body)
        log_events = [e for e in events if e["type"] == "log"]

        # At least some log events should be present.
        assert len(log_events) > 0

        # Each log event has message, level, and logger.
        for le in log_events:
            data = le["data"]
            assert "message" in data
            assert "level" in data
            assert "logger" in data

    def test_pipeline_sse_includes_synthesized_stages(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """SSE stream includes synthesized sub-stages 1b (memory) and 1c (calendar)."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_ACCOUNT_EMAIL", "test@example.com")
        monkeypatch.setenv("OWNER_NAME", "TestOwner")

        with (
            patch("cal_ai.web.app.load_dotenv"),
            patch("cal_ai.web.routes.load_settings") as mock_settings,
        ):
            settings_mock = MagicMock()
            settings_mock.owner_name = "TestOwner"
            mock_settings.return_value = settings_mock

            app = create_app()
            client = TestClient(app)

            with (
                patch(
                    "cal_ai.web.routes.run_pipeline",
                    side_effect=_run_mock_pipeline,
                ),
                client.stream(
                    "POST",
                    "/api/pipeline/run",
                    data={"text": "[Alice]: Meeting tomorrow."},
                ) as response,
            ):
                body = response.read().decode("utf-8")

        events = _parse_sse_events(body)
        stage_events = [e for e in events if e["type"] == "stage"]
        stage_names = [e["data"]["name"] for e in stage_events]

        # Check that 1b and 1c sub-stages are present.
        assert "1b_memory" in stage_names
        assert "1c_calendar" in stage_names

    def test_pipeline_rejects_oversized_upload(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST /api/pipeline/run returns error SSE event for files > 10 MB."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_ACCOUNT_EMAIL", "test@example.com")
        monkeypatch.setenv("OWNER_NAME", "TestOwner")

        # Create a file just over the 10 MB limit.
        import io

        from cal_ai.web.routes import _MAX_UPLOAD_BYTES

        oversized = b"x" * (_MAX_UPLOAD_BYTES + 1)

        with patch("cal_ai.web.app.load_dotenv"):
            app = create_app()
            client = TestClient(app)

            with client.stream(
                "POST",
                "/api/pipeline/run",
                files={
                    "file": (
                        "big.txt",
                        io.BytesIO(oversized),
                        "text/plain",
                    )
                },
            ) as response:
                body = response.read().decode("utf-8")

        events = _parse_sse_events(body)
        event_types = [e["type"] for e in events]
        assert "error" in event_types
        assert "done" in event_types
        error_event = next(e for e in events if e["type"] == "error")
        assert "10 MB" in error_event["data"]["message"]

    def test_pipeline_error_returns_error_event(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Pipeline exception produces an event:error in the SSE stream."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_ACCOUNT_EMAIL", "test@example.com")
        monkeypatch.setenv("OWNER_NAME", "TestOwner")

        def _raise_pipeline(*args, **kwargs):
            raise RuntimeError("Pipeline exploded")

        with (
            patch("cal_ai.web.app.load_dotenv"),
            patch("cal_ai.web.routes.load_settings") as mock_settings,
        ):
            settings_mock = MagicMock()
            settings_mock.owner_name = "TestOwner"
            mock_settings.return_value = settings_mock

            app = create_app()
            client = TestClient(app)

            with (
                patch(
                    "cal_ai.web.routes.run_pipeline",
                    side_effect=_raise_pipeline,
                ),
                client.stream(
                    "POST",
                    "/api/pipeline/run",
                    data={"text": "[Alice]: Meeting."},
                ) as response,
            ):
                body = response.read().decode("utf-8")

        events = _parse_sse_events(body)
        event_types = [e["type"] for e in events]
        assert "error" in event_types
        assert "done" in event_types

        error_event = next(e for e in events if e["type"] == "error")
        assert "Pipeline exploded" in error_event["data"]["message"]


# ---------------------------------------------------------------------------
# Memory API endpoint tests
# ---------------------------------------------------------------------------


class TestMemoryAPI:
    """Tests for the ``GET /api/memories`` endpoint."""

    def test_memories_returns_empty_when_no_config(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GET /api/memories returns [] when config is unavailable."""
        from cal_ai.config import ConfigError

        with (
            patch("cal_ai.web.app.load_dotenv"),
            patch(
                "cal_ai.web.routes.load_memory_settings",
                side_effect=ConfigError("Missing OWNER_NAME"),
            ),
        ):
            app = create_app()
            client = TestClient(app)

            response = client.get("/api/memories")

        assert response.status_code == 200
        assert response.json() == []

    def test_memories_returns_empty_when_no_db_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """GET /api/memories returns [] when DB file doesn't exist."""
        monkeypatch.setenv("MEMORY_DB_PATH", str(tmp_path / "nonexistent.db"))

        with patch("cal_ai.web.app.load_dotenv"):
            app = create_app()
        client = TestClient(app)

        response = client.get("/api/memories")

        assert response.status_code == 200
        assert response.json() == []

    def test_memories_returns_stored_memories(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """GET /api/memories returns flat array with stored memories."""
        from cal_ai.memory.store import MemoryStore

        db_path = tmp_path / "test_memory.db"
        store = MemoryStore(str(db_path))
        store.upsert("preferences", "coffee", "likes lattes", "high")
        store.upsert("people", "bob", "prefers mornings", "medium")
        store.close()

        monkeypatch.setenv("MEMORY_DB_PATH", str(db_path))

        with patch("cal_ai.web.app.load_dotenv"):
            app = create_app()
        client = TestClient(app)

        response = client.get("/api/memories")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Check field structure.
        for entry in data:
            assert "category" in entry
            assert "key" in entry
            assert "value" in entry
            assert "confidence" in entry
            assert "id" not in entry
            assert "source_count" not in entry
            assert "created_at" not in entry
            assert "updated_at" not in entry

    def test_memories_ordered_by_category_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """GET /api/memories returns entries ordered by category then key."""
        from cal_ai.memory.store import MemoryStore

        db_path = tmp_path / "test_memory.db"
        store = MemoryStore(str(db_path))
        store.upsert("vocabulary", "standup", "daily meeting", "medium")
        store.upsert("people", "zoe", "designer", "medium")
        store.upsert("people", "alice", "manager", "high")
        store.close()

        monkeypatch.setenv("MEMORY_DB_PATH", str(db_path))

        with patch("cal_ai.web.app.load_dotenv"):
            app = create_app()
        client = TestClient(app)

        response = client.get("/api/memories")
        data = response.json()

        # people.alice should come before people.zoe, then vocabulary.standup
        categories = [d["category"] for d in data]
        assert categories == ["people", "people", "vocabulary"]
        assert data[0]["key"] == "alice"
        assert data[1]["key"] == "zoe"


# ---------------------------------------------------------------------------
# SSE parsing helper
# ---------------------------------------------------------------------------


def _parse_sse_events(body: str) -> list[dict]:
    """Parse an SSE body string into a list of event dicts.

    Each dict has ``type`` (str) and ``data`` (parsed JSON dict).
    """
    events = []
    current_type = None
    current_data = None

    for line in body.split("\n"):
        if line.startswith("event: "):
            current_type = line[len("event: ") :]
        elif line.startswith("data: "):
            current_data = line[len("data: ") :]
        elif line == "" and current_type is not None and current_data is not None:
            try:
                events.append({"type": current_type, "data": json.loads(current_data)})
            except json.JSONDecodeError:
                events.append({"type": current_type, "data": current_data})
            current_type = None
            current_data = None

    return events
