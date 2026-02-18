"""Entry point for ``python -m cal_ai``.

Provides a CLI that accepts a transcript file and runs the full
conversation-to-calendar pipeline.  Uses stdlib :mod:`argparse` for
argument parsing (no extra dependencies).

Exit codes:
    0 -- Pipeline completed successfully (including zero events).
    1 -- An error occurred (file not found, unreadable, config error).
    2 -- Argument parsing error (handled by argparse).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cal_ai.config import ConfigError, load_settings
from cal_ai.demo_output import print_pipeline_result
from cal_ai.log import setup_logging
from cal_ai.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser.

    Returns:
        Configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="cal-ai",
        description="Extract calendar events from a conversation transcript.",
    )
    parser.add_argument(
        "transcript_file",
        type=str,
        help="Path to the .txt transcript file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Parse and extract events but skip calendar sync.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Enable debug-level logging.",
    )
    parser.add_argument(
        "--owner",
        type=str,
        default=None,
        help="Override the calendar owner name (defaults to OWNER_NAME from config).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the cal-ai CLI.

    Args:
        argv: Command-line arguments.  Defaults to ``sys.argv[1:]``
            when ``None`` (the normal case).

    Returns:
        Exit code: ``0`` on success, ``1`` on error.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # --- Configure logging ---------------------------------------------------
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level)

    # --- Validate transcript file ---------------------------------------------
    transcript_path = Path(args.transcript_file)

    if not transcript_path.exists():
        print(f"Error: File not found: {transcript_path}", file=sys.stderr)
        return 1

    if not transcript_path.is_file():
        print(f"Error: Not a file: {transcript_path}", file=sys.stderr)
        return 1

    # Check readability by attempting to open the file.
    try:
        with open(transcript_path) as f:
            f.read(1)
    except PermissionError:
        print(
            f"Error: Permission denied: {transcript_path}",
            file=sys.stderr,
        )
        return 1

    # --- Resolve owner name ---------------------------------------------------
    owner = args.owner
    if owner is None:
        try:
            settings = load_settings()
            owner = settings.owner_name
        except ConfigError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    # --- Run pipeline ---------------------------------------------------------
    try:
        result = run_pipeline(
            transcript_path=transcript_path,
            owner=owner,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, PermissionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # --- Render demo output ---------------------------------------------------
    print_pipeline_result(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
