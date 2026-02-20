"""Regression test infrastructure: auto-discovery, markers, and CLI flags.

Provides:
- ``--live`` CLI flag to enable live Gemini API tests.
- ``live``, ``regression``, and ``slow`` marker registration.
- ``pytest_collection_modifyitems`` to skip ``@pytest.mark.live`` tests
  unless ``--live`` is passed.
- ``pytest_generate_tests`` for automatic parametrization of
  ``sample_case`` fixtures from ``samples/**/*.expected.json`` sidecar files.
- Auto-application of ``@pytest.mark.slow`` for tests from ``samples/long/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.regression.loader import discover_samples
from tests.regression.schema import SidecarSpec

# Root of the samples directory (relative to the project root).
_SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "samples"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the ``--live`` CLI flag for live Gemini API tests."""
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run live regression tests against real Gemini API.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers to avoid ``PytestUnknownMarkWarning``."""
    config.addinivalue_line("markers", "live: requires real Gemini API credentials")
    config.addinivalue_line("markers", "regression: regression test suite")
    config.addinivalue_line("markers", "slow: long-running test")


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Skip ``@pytest.mark.live`` tests unless ``--live`` is passed."""
    if config.getoption("--live"):
        return

    skip_live = pytest.mark.skip(reason="Need --live option to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Auto-parametrize tests that request a ``sample_case`` fixture.

    Discovers all ``samples/**/*.txt`` files paired with a sibling
    ``.expected.json`` sidecar, and parametrizes the test with
    ``(txt_path, sidecar)`` tuples.  Test IDs use ``category/stem``
    format for easy ``-k`` filtering (e.g., ``-k crud/simple_lunch``).

    Tests from the ``samples/long/`` directory are automatically
    tagged with ``@pytest.mark.slow``.
    """
    if "sample_case" not in metafunc.fixturenames:
        return

    cases = discover_samples(_SAMPLES_DIR)

    if not cases:
        pytest.skip("No sample/sidecar pairs found")
        return

    ids: list[str] = []
    argvalues: list[tuple[Path, SidecarSpec]] = []
    marks_list: list[list[pytest.MarkDecorator]] = []

    for txt_path, sidecar in cases:
        # Build test ID as category/stem (e.g., "crud/simple_lunch").
        rel = txt_path.relative_to(_SAMPLES_DIR)
        test_id = f"{rel.parent}/{rel.stem}"

        ids.append(test_id)
        argvalues.append((txt_path, sidecar))

        # Auto-apply @pytest.mark.slow for samples in the long/ directory.
        item_marks: list[pytest.MarkDecorator] = []
        if "long" in rel.parts:
            item_marks.append(pytest.mark.slow)
        marks_list.append(item_marks)

    # Apply marks to individual parametrize values.
    # Note: sample_case is a single tuple parameter, so we pass each value
    # wrapped in pytest.param() WITHOUT unpacking (no *val).
    marked_argvalues = [
        pytest.param(val, marks=mrks)
        for val, mrks in zip(argvalues, marks_list, strict=True)
    ]

    metafunc.parametrize(
        "sample_case",
        marked_argvalues,
        ids=ids,
    )
