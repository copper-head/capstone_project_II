"""Parametrized regression tests for the AI extraction pipeline.

Two test functions cover mock mode (default) and live mode (``--live``):

- ``test_mock_extraction`` -- patches ``genai.Client.models.generate_content``
  with the sidecar's ``mock_llm_response`` and ``fetch_calendar_context``
  with the sidecar's calendar context.  Runs ``run_pipeline(dry_run=True)``
  and asserts via the tolerance engine.

- ``test_live_extraction`` -- same flow but does NOT mock the LLM call.
  Requires a real ``GEMINI_API_KEY`` env var and the ``--live`` flag.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cal_ai.models.extraction import ExtractionResult
from cal_ai.pipeline import run_pipeline
from tests.regression.loader import build_calendar_context
from tests.regression.schema import SidecarSpec
from tests.regression.tolerance import assert_extraction_result

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_mock_response(sidecar: SidecarSpec) -> MagicMock:
    """Build a mock ``generate_content`` return value from sidecar data.

    The mock response's ``.text`` attribute returns the JSON-serialized
    ``mock_llm_response`` from the sidecar, mimicking the Gemini SDK
    response object.

    Args:
        sidecar: A validated sidecar spec with ``mock_llm_response``.

    Returns:
        A ``MagicMock`` that behaves like a Gemini response object.
    """
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(sidecar.mock_llm_response)
    return mock_resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_mock_extraction(
    sample_case: tuple[Path, SidecarSpec],
    monkeypatch_env: dict[str, str],
) -> None:
    """Mock mode: patch LLM and calendar context, then assert extraction.

    Steps:
    1. Load sidecar (provided by ``sample_case`` via ``pytest_generate_tests``).
    2. Build ``CalendarContext`` from sidecar's ``calendar_context`` entries.
    3. Patch ``genai.Client.models.generate_content`` to return the sidecar's
       ``mock_llm_response``.
    4. Patch ``cal_ai.pipeline.fetch_calendar_context`` to return the built
       ``CalendarContext``.
    5. Call ``run_pipeline()`` with ``dry_run=True``.
    6. Assert the extraction result via ``assert_extraction_result()``.
    """
    txt_path, sidecar = sample_case
    ref_dt = datetime.fromisoformat(sidecar.reference_datetime)
    cal_ctx = build_calendar_context(sidecar)

    mock_resp = _build_mock_response(sidecar)

    with (
        patch(
            "cal_ai.llm.genai.Client",
        ) as mock_genai_cls,
        patch(
            "cal_ai.pipeline.fetch_calendar_context",
            return_value=cal_ctx,
        ),
        patch(
            "cal_ai.pipeline.get_calendar_credentials",
            return_value=MagicMock(),
        ),
    ):
        # Wire the mocked generate_content onto the client instance.
        mock_genai_instance = mock_genai_cls.return_value
        mock_genai_instance.models.generate_content.return_value = mock_resp

        result = run_pipeline(
            transcript_path=txt_path,
            owner=sidecar.owner,
            dry_run=True,
            current_datetime=ref_dt,
        )

    # Build ExtractionResult from pipeline's events_extracted for assertion.
    extraction = ExtractionResult(
        events=result.events_extracted,
        summary="mock extraction",
    )

    assert_extraction_result(extraction, sidecar)


@pytest.mark.regression
@pytest.mark.live
def test_live_extraction(
    sample_case: tuple[Path, SidecarSpec],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live mode: real Gemini API call, then assert extraction with tolerance.

    Same flow as ``test_mock_extraction`` but does NOT patch
    ``generate_content``.  Requires:
    - A real ``GEMINI_API_KEY`` environment variable.
    - The ``--live`` pytest flag.

    Calendar context is still built from the sidecar (not a real Google
    Calendar) so tests remain reproducible.

    Note: This test uses ``monkeypatch`` directly (not ``monkeypatch_env``)
    so the real ``GEMINI_API_KEY`` from the environment is preserved.
    """
    import os

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        pytest.skip("Real GEMINI_API_KEY required for live tests")

    # Patch load_dotenv so .env file does not override test env.
    monkeypatch.setattr("cal_ai.config.load_dotenv", lambda *_a, **_kw: None)
    # Set required env vars that load_settings() needs.
    monkeypatch.setenv("GEMINI_API_KEY", api_key)
    monkeypatch.setenv("GOOGLE_ACCOUNT_EMAIL", "test@example.com")
    monkeypatch.setenv("OWNER_NAME", "Test User")

    txt_path, sidecar = sample_case
    ref_dt = datetime.fromisoformat(sidecar.reference_datetime)
    cal_ctx = build_calendar_context(sidecar)

    with (
        patch(
            "cal_ai.pipeline.fetch_calendar_context",
            return_value=cal_ctx,
        ),
        patch(
            "cal_ai.pipeline.get_calendar_credentials",
            return_value=MagicMock(),
        ),
    ):
        result = run_pipeline(
            transcript_path=txt_path,
            owner=sidecar.owner,
            dry_run=True,
            current_datetime=ref_dt,
        )

    extraction = ExtractionResult(
        events=result.events_extracted,
        summary="live extraction",
    )

    assert_extraction_result(extraction, sidecar)
