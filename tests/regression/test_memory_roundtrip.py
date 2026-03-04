"""Memory round-trip regression tests: dual-pass extraction with/without memory.

Discovers paired samples in ``samples/memory/`` (A/B convention) and runs
two extraction passes per B-sample:

- **Pass 1 (with memory)**: Memory context injected via patched
  ``MemoryStore.load_all()`` -> assert against ``expected_events``.
- **Pass 2 (without memory)**: Empty memory -> assert against
  ``expected_events_no_memory``.

Two test functions:

- ``test_memory_mock_roundtrip`` -- deterministic mock mode (default).
- ``test_memory_live_roundtrip`` -- real Gemini API (``--live`` flag).

Uses **inline** ``pytest_generate_tests`` (no separate conftest) so that
memory sample discovery is self-contained in this file.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cal_ai.memory.formatter import format_memory_context
from cal_ai.models.extraction import ExtractionResult
from cal_ai.pipeline import run_pipeline
from tests.regression.loader import build_calendar_context, load_sidecar
from tests.regression.schema import SidecarSpec
from tests.regression.tolerance import assert_extraction_result

# ---------------------------------------------------------------------------
# Sample directory
# ---------------------------------------------------------------------------

_MEMORY_SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "samples" / "memory"


# ---------------------------------------------------------------------------
# Inline pytest_generate_tests — discovers B-samples and pairs with A
# ---------------------------------------------------------------------------


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Auto-parametrize tests requesting a ``memory_pair`` fixture.

    Globs ``samples/memory/*_b.txt``, derives the A-file by replacing
    ``_b.txt`` with ``_a.txt``, loads both sidecars, and parametrizes
    with ``(b_txt_path, b_sidecar)`` tuples.

    Test IDs use the stem minus the ``_b`` suffix (e.g., ``pref_time``).
    """
    if "memory_pair" not in metafunc.fixturenames:
        return

    if not _MEMORY_SAMPLES_DIR.exists():
        metafunc.parametrize("memory_pair", [], ids=[])
        return

    b_files = sorted(_MEMORY_SAMPLES_DIR.glob("*_b.txt"))

    if not b_files:
        metafunc.parametrize("memory_pair", [], ids=[])
        return

    ids: list[str] = []
    argvalues: list[tuple[Path, SidecarSpec]] = []

    for b_txt in b_files:
        # Derive A-partner and validate its sidecar exists and parses.
        a_txt = b_txt.with_name(b_txt.name.replace("_b.txt", "_a.txt"))
        assert a_txt.exists(), f"Memory pair missing A-file: {a_txt} (partner for {b_txt})"

        a_sidecar_path = a_txt.with_suffix(".expected.json")
        assert a_sidecar_path.exists(), f"Memory pair missing A-sidecar: {a_sidecar_path}"
        load_sidecar(a_sidecar_path)  # Validate schema; A-sidecar is documentation-only.

        # Load B-sidecar.
        b_sidecar_path = b_txt.with_suffix(".expected.json")
        assert b_sidecar_path.exists(), f"Memory pair missing B-sidecar: {b_sidecar_path}"
        b_sidecar = load_sidecar(b_sidecar_path)

        # Validate B-sidecar has the required dual-outcome fields.
        assert b_sidecar.expected_events_no_memory is not None, (
            f"{b_sidecar_path.name}: expected_events_no_memory is required"
        )
        assert b_sidecar.mock_llm_response_no_memory is not None, (
            f"{b_sidecar_path.name}: mock_llm_response_no_memory is required"
        )

        # Test ID: stem minus the _b suffix.
        test_id = b_txt.stem.removesuffix("_b")
        ids.append(test_id)
        argvalues.append((b_txt, b_sidecar))

    metafunc.parametrize("memory_pair", argvalues, ids=ids)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_mock_response_from_dict(response_dict: dict) -> MagicMock:
    """Build a mock ``generate_content`` return value from a raw dict."""
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(response_dict)
    return mock_resp


def _make_no_memory_sidecar(sidecar: SidecarSpec) -> SidecarSpec:
    """Create a copy of *sidecar* with ``expected_events`` swapped.

    Returns a new ``SidecarSpec`` whose ``expected_events`` is set to
    the original's ``expected_events_no_memory``.  All other fields
    (tolerance, calendar_context, etc.) are preserved.
    """
    data = sidecar.model_dump()
    data["expected_events"] = data.pop("expected_events_no_memory") or []
    # Remove fields not needed for the tolerance engine.
    data.pop("mock_llm_response_no_memory", None)
    data.pop("expected_memory_facts", None)
    return SidecarSpec.model_validate(data)


def _run_mock_pass(
    txt_path: Path,
    sidecar: SidecarSpec,
    memory_entries: list,
    mock_llm_response: dict,
) -> ExtractionResult:
    """Execute a single mock pipeline pass and return the ExtractionResult."""
    ref_dt = datetime.fromisoformat(sidecar.reference_datetime)
    cal_ctx = build_calendar_context(sidecar)
    mock_resp = _build_mock_response_from_dict(mock_llm_response)

    mock_memory_store = MagicMock()
    mock_memory_store.load_all.return_value = memory_entries
    mock_memory_store_cls = MagicMock(return_value=mock_memory_store)

    mock_format_memory = MagicMock(
        side_effect=lambda memories, owner: format_memory_context(memories, owner)
    )

    with (
        patch("cal_ai.llm.genai.Client") as mock_genai_cls,
        patch("cal_ai.pipeline.fetch_calendar_context", return_value=cal_ctx),
        patch("cal_ai.pipeline.get_calendar_credentials", return_value=MagicMock()),
        patch("cal_ai.pipeline.MemoryStore", mock_memory_store_cls),
        patch("cal_ai.pipeline.format_memory_context", mock_format_memory),
        patch(
            "cal_ai.pipeline._resolve_memory_db_path",
            return_value="/tmp/regression_test_memory.db",
        ),
        patch(
            "cal_ai.pipeline.run_memory_write",
            return_value=MagicMock(
                memories_added=0,
                memories_updated=0,
                memories_deleted=0,
                usage_metadata=[],
            ),
        ),
    ):
        mock_genai_instance = mock_genai_cls.return_value
        mock_genai_instance.models.generate_content.return_value = mock_resp

        result = run_pipeline(
            transcript_path=txt_path,
            owner=sidecar.owner,
            dry_run=True,
            current_datetime=ref_dt,
        )

    return ExtractionResult(
        events=result.events_extracted,
        summary="mock extraction",
    )


def _run_live_pass(
    txt_path: Path,
    sidecar: SidecarSpec,
    memory_entries: list,
    monkeypatch: pytest.MonkeyPatch,
) -> ExtractionResult:
    """Execute a single live pipeline pass and return the ExtractionResult."""
    import os

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        pytest.skip("Real GEMINI_API_KEY required for live tests")

    monkeypatch.setattr("cal_ai.config.load_dotenv", lambda *_a, **_kw: None)
    monkeypatch.setenv("GEMINI_API_KEY", api_key)
    monkeypatch.setenv("GOOGLE_ACCOUNT_EMAIL", "test@example.com")
    monkeypatch.setenv("OWNER_NAME", sidecar.owner)

    ref_dt = datetime.fromisoformat(sidecar.reference_datetime)
    cal_ctx = build_calendar_context(sidecar)

    mock_memory_store = MagicMock()
    mock_memory_store.load_all.return_value = memory_entries
    mock_memory_store_cls = MagicMock(return_value=mock_memory_store)

    mock_format_memory = MagicMock(
        side_effect=lambda memories, owner: format_memory_context(memories, owner)
    )

    with (
        patch("cal_ai.pipeline.fetch_calendar_context", return_value=cal_ctx),
        patch("cal_ai.pipeline.get_calendar_credentials", return_value=MagicMock()),
        patch("cal_ai.pipeline.MemoryStore", mock_memory_store_cls),
        patch("cal_ai.pipeline.format_memory_context", mock_format_memory),
        patch(
            "cal_ai.pipeline._resolve_memory_db_path",
            return_value="/tmp/regression_test_memory.db",
        ),
    ):
        result = run_pipeline(
            transcript_path=txt_path,
            owner=sidecar.owner,
            dry_run=True,
            current_datetime=ref_dt,
        )

    return ExtractionResult(
        events=result.events_extracted,
        summary="live extraction",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.memory
def test_memory_mock_roundtrip(
    memory_pair: tuple[Path, SidecarSpec],
    monkeypatch_env: dict[str, str],
) -> None:
    """Mock mode: dual-pass extraction with and without memory context.

    Pass 1 -- with memory: patches ``MemoryStore.load_all()`` to return
    the B-sidecar's ``memory_context`` and asserts against ``expected_events``.

    Pass 2 -- without memory: patches ``MemoryStore.load_all()`` to return
    ``[]`` and asserts against ``expected_events_no_memory``.
    """
    txt_path, sidecar = memory_pair
    memory_entries = sidecar.memory_context or []

    # --- Pass 1: with memory ---
    extraction_with = _run_mock_pass(txt_path, sidecar, memory_entries, sidecar.mock_llm_response)
    assert_extraction_result(extraction_with, sidecar)

    # --- Pass 2: without memory ---
    no_mem_sidecar = _make_no_memory_sidecar(sidecar)
    extraction_without = _run_mock_pass(
        txt_path, no_mem_sidecar, [], sidecar.mock_llm_response_no_memory
    )
    assert_extraction_result(extraction_without, no_mem_sidecar)


@pytest.mark.regression
@pytest.mark.memory
@pytest.mark.live
def test_memory_live_roundtrip(
    memory_pair: tuple[Path, SidecarSpec],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live mode: dual-pass extraction with real Gemini API.

    Same dual-pass structure as mock mode but with real LLM calls.
    Both passes use moderate tolerance.  Requires ``--live`` flag.
    """
    txt_path, sidecar = memory_pair
    memory_entries = sidecar.memory_context or []

    # --- Pass 1: with memory ---
    extraction_with = _run_live_pass(txt_path, sidecar, memory_entries, monkeypatch)
    assert_extraction_result(extraction_with, sidecar)

    # --- Pass 2: without memory ---
    no_mem_sidecar = _make_no_memory_sidecar(sidecar)
    extraction_without = _run_live_pass(txt_path, no_mem_sidecar, [], monkeypatch)
    assert_extraction_result(extraction_without, no_mem_sidecar)
