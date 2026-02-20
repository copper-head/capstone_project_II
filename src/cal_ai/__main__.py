"""Entry point for ``python -m cal_ai``.

Provides a CLI that accepts a transcript file and runs the full
conversation-to-calendar pipeline.  Uses stdlib :mod:`argparse` for
argument parsing (no extra dependencies).

Subcommands:
    run       -- Default. Process a transcript and sync to calendar.
    benchmark -- Run the benchmark suite against sample transcripts.

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
    """Build and return the CLI argument parser with subcommands.

    Returns:
        Configured :class:`argparse.ArgumentParser` with ``run`` and
        ``benchmark`` subcommands.
    """
    parser = argparse.ArgumentParser(
        prog="cal-ai",
        description=(
            "Extract calendar events from a conversation transcript."
        ),
    )

    subparsers = parser.add_subparsers(dest="command")

    # --- "run" subcommand (default) -----------------------------------
    run_parser = subparsers.add_parser(
        "run",
        help="Process a transcript and sync to calendar.",
    )
    run_parser.add_argument(
        "transcript_file",
        type=str,
        help="Path to the .txt transcript file.",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Parse and extract events but skip calendar sync.",
    )
    run_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Enable debug-level logging.",
    )
    run_parser.add_argument(
        "--owner",
        type=str,
        default=None,
        help=(
            "Override the calendar owner name "
            "(defaults to OWNER_NAME from config)."
        ),
    )

    # --- "benchmark" subcommand ---------------------------------------
    bench_parser = subparsers.add_parser(
        "benchmark",
        help="Run the benchmark suite against sample transcripts.",
    )
    bench_parser.add_argument(
        "directory",
        nargs="?",
        default="samples/",
        help=(
            "Directory containing sample transcripts "
            "(default: samples/)."
        ),
    )
    bench_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Directory for report output (default: reports/).",
    )
    bench_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Enable debug-level logging.",
    )

    return parser


def _resolve_command(
    parser: argparse.ArgumentParser,
    argv: list[str],
) -> argparse.Namespace:
    """Parse *argv* with implicit ``run`` subcommand for backward compat.

    If the first token is not a known subcommand (whether it is a
    positional path or an option flag like ``--dry-run``), the ``run``
    subcommand is prepended so that ``python -m cal_ai file.txt`` and
    ``python -m cal_ai --dry-run file.txt`` continue to work.

    Args:
        parser: The top-level argument parser.
        argv: Command-line arguments.

    Returns:
        Parsed :class:`argparse.Namespace`.
    """
    known_subcommands = {"run", "benchmark"}
    if not argv:
        # No arguments at all -- let the "run" subparser handle the error
        # so the user sees usage for the run subcommand.
        argv = ["run"]
    elif argv[0] in {"-h", "--help"}:
        # Let the top-level parser handle help display so both
        # subcommands are shown.
        pass
    elif argv[0] not in known_subcommands:
        argv = ["run", *argv]

    return parser.parse_args(argv)


def _handle_run(args: argparse.Namespace) -> int:
    """Execute the ``run`` subcommand.

    Args:
        args: Parsed arguments from the ``run`` subparser.

    Returns:
        Exit code: ``0`` on success, ``1`` on error.
    """
    # --- Validate transcript file -------------------------------------
    transcript_path = Path(args.transcript_file)

    if not transcript_path.exists():
        print(
            f"Error: File not found: {transcript_path}", file=sys.stderr
        )
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

    # --- Resolve owner name -------------------------------------------
    owner = args.owner
    if owner is None:
        try:
            settings = load_settings()
            owner = settings.owner_name
        except ConfigError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    # --- Run pipeline -------------------------------------------------
    try:
        result = run_pipeline(
            transcript_path=transcript_path,
            owner=owner,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, PermissionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # --- Render demo output -------------------------------------------
    print_pipeline_result(result)

    return 0


def _handle_benchmark(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Execute the ``benchmark`` subcommand (stub).

    The actual benchmark logic will be implemented in a later task.

    Args:
        args: Parsed arguments from the ``benchmark`` subparser.

    Returns:
        Exit code: ``0``.
    """
    print("Benchmark: Not implemented yet.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the cal-ai CLI.

    Args:
        argv: Command-line arguments.  Defaults to ``sys.argv[1:]``
            when ``None`` (the normal case).

    Returns:
        Exit code: ``0`` on success, ``1`` on error.
    """
    parser = build_parser()
    args = _resolve_command(parser, argv if argv is not None else sys.argv[1:])

    # --- Configure logging --------------------------------------------
    log_level = "DEBUG" if getattr(args, "verbose", False) else "INFO"
    setup_logging(log_level)

    # --- Dispatch to subcommand handler -------------------------------
    if args.command == "benchmark":
        return _handle_benchmark(args)

    # Default: "run" subcommand (including implicit routing).
    return _handle_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
