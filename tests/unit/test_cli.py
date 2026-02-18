"""Unit tests for the CLI entrypoint (7 tests).

Tests cover: valid file invocation, missing arguments, nonexistent file,
--dry-run flag, --verbose / -v flag, --owner override, and unreadable file.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cal_ai.__main__ import main
from cal_ai.pipeline import PipelineResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transcript(tmp_path: Path, name: str = "sample.txt") -> Path:
    """Create a minimal transcript file and return its path."""
    transcript = tmp_path / name
    transcript.write_text("[Alice]: Hey, want to grab lunch?\n[Bob]: Sure!\n")
    return transcript


def _dummy_pipeline_result(transcript_path: Path) -> PipelineResult:
    """Return a minimal ``PipelineResult`` for mocking ``run_pipeline``."""
    return PipelineResult(transcript_path=transcript_path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCLI:
    """Unit tests for ``cal_ai.__main__.main``."""

    def test_cli_valid_file_runs_pipeline(
        self,
        tmp_path: Path,
        monkeypatch_env: dict[str, str],
    ) -> None:
        """Valid file -> pipeline invoked, exit code 0."""
        transcript = _make_transcript(tmp_path)
        mock_result = _dummy_pipeline_result(transcript)

        with (
            patch("cal_ai.__main__.run_pipeline", return_value=mock_result) as mock_run,
            patch("cal_ai.__main__.print_pipeline_result") as mock_print,
        ):
            exit_code = main([str(transcript)])

        assert exit_code == 0
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs["transcript_path"] == transcript
        mock_print.assert_called_once_with(mock_result)

    def test_cli_missing_file_argument_shows_usage(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """No arguments -> exit code 2, stderr contains 'usage'."""
        with pytest.raises(SystemExit) as exc_info:
            main([])

        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "usage" in captured.err.lower()

    def test_cli_nonexistent_file_shows_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Nonexistent file -> exit code 1, stderr contains 'File not found'."""
        bad_path = tmp_path / "does_not_exist.txt"

        exit_code = main([str(bad_path)])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "File not found" in captured.err

    def test_cli_dry_run_flag_passes_to_pipeline(
        self,
        tmp_path: Path,
        monkeypatch_env: dict[str, str],
    ) -> None:
        """--dry-run -> run_pipeline called with dry_run=True."""
        transcript = _make_transcript(tmp_path)
        mock_result = _dummy_pipeline_result(transcript)

        with (
            patch("cal_ai.__main__.run_pipeline", return_value=mock_result) as mock_run,
            patch("cal_ai.__main__.print_pipeline_result"),
        ):
            exit_code = main(["--dry-run", str(transcript)])

        assert exit_code == 0
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["dry_run"] is True

    def test_cli_verbose_flag_sets_debug_logging(
        self,
        tmp_path: Path,
        monkeypatch_env: dict[str, str],
    ) -> None:
        """-v flag -> setup_logging called with 'DEBUG'."""
        transcript = _make_transcript(tmp_path)
        mock_result = _dummy_pipeline_result(transcript)

        with (
            patch("cal_ai.__main__.run_pipeline", return_value=mock_result),
            patch("cal_ai.__main__.print_pipeline_result"),
            patch("cal_ai.__main__.setup_logging") as mock_setup,
        ):
            exit_code = main(["-v", str(transcript)])

        assert exit_code == 0
        mock_setup.assert_called_once_with("DEBUG")

    def test_cli_owner_override(
        self,
        tmp_path: Path,
        monkeypatch_env: dict[str, str],
    ) -> None:
        """--owner 'Bob' -> run_pipeline called with owner='Bob'."""
        transcript = _make_transcript(tmp_path)
        mock_result = _dummy_pipeline_result(transcript)

        with (
            patch("cal_ai.__main__.run_pipeline", return_value=mock_result) as mock_run,
            patch("cal_ai.__main__.print_pipeline_result"),
        ):
            exit_code = main(["--owner", "Bob", str(transcript)])

        assert exit_code == 0
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["owner"] == "Bob"

    @pytest.mark.skipif(
        os.getuid() == 0,
        reason="Root user can read any file; permission test is meaningless.",
    )
    def test_cli_unreadable_file_shows_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Unreadable file -> exit code 1, stderr contains 'Permission denied'."""
        transcript = _make_transcript(tmp_path)
        # Remove read permission.
        transcript.chmod(stat.S_IWUSR)

        try:
            exit_code = main([str(transcript)])

            assert exit_code == 1
            captured = capsys.readouterr()
            assert "Permission denied" in captured.err
        finally:
            # Restore permissions so tmp_path cleanup does not fail.
            transcript.chmod(stat.S_IRUSR | stat.S_IWUSR)
