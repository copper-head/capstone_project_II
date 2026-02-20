"""Benchmark runner for live Gemini extraction scoring.

Discovers sample transcripts, executes live LLM extraction with sidecar
calendar context, scores results against expected events, and tracks
latency/token usage for cost estimation.

Key functions:
    :func:`discover_samples` -- find all .txt files with optional sidecars.
    :func:`run_benchmark` -- orchestrate extraction, scoring, and reporting.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from cal_ai.benchmark.scoring import (
    AggregateScore,
    SampleScore,
    aggregate_scores,
    calibrate_confidence,
    score_sample,
)
from cal_ai.llm import GeminiClient
from cal_ai.models.extraction import ExtractionResult
from tests.regression.loader import build_calendar_context, load_sidecar
from tests.regression.schema import SidecarSpec

logger = logging.getLogger(__name__)

# Gemini 2.5 pricing per 1M tokens (<=200k context).
_PROMPT_COST_PER_1M = 1.25
_OUTPUT_COST_PER_1M = 10.00


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SampleResult:
    """Result of running a single benchmark sample.

    Attributes:
        sample_name: Identifier like ``"crud/simple_lunch"``.
        category: Sample category (e.g. ``"crud"``).
        txt_path: Path to the transcript file.
        has_sidecar: Whether a sidecar was found.
        extraction: The raw extraction result from Gemini.
        score: The P/R/F1 score (``None`` if no sidecar).
        latency_s: Wall-clock time for the extraction call.
        prompt_tokens: Total prompt tokens across all API attempts.
        output_tokens: Total output tokens (candidates) across attempts.
        thoughts_tokens: Total thinking tokens across attempts.
        error: Error message if extraction failed.
    """

    sample_name: str
    category: str
    txt_path: Path
    has_sidecar: bool = False
    extraction: ExtractionResult | None = None
    score: SampleScore | None = None
    latency_s: float = 0.0
    prompt_tokens: int = 0
    output_tokens: int = 0
    thoughts_tokens: int = 0
    error: str | None = None


@dataclass
class BenchmarkResult:
    """Aggregate result of a full benchmark run.

    Attributes:
        sample_results: Per-sample results.
        aggregate: Aggregated P/R/F1 scores.
        confidence_calibration: Confidence-to-accuracy mapping.
        total_prompt_tokens: Sum of prompt tokens across all samples.
        total_output_tokens: Sum of output tokens across all samples.
        total_thoughts_tokens: Sum of thinking tokens across all samples.
        total_latency_s: Sum of latency across all samples.
        est_cost_usd: Estimated total cost in USD.
        model: Model name used for extraction.
        timestamp: ISO 8601 timestamp of the run.
    """

    sample_results: list[SampleResult] = field(default_factory=list)
    aggregate: AggregateScore | None = None
    confidence_calibration: dict[str, float] = field(default_factory=dict)
    total_prompt_tokens: int = 0
    total_output_tokens: int = 0
    total_thoughts_tokens: int = 0
    total_latency_s: float = 0.0
    est_cost_usd: float = 0.0
    model: str = "gemini-2.5-pro"
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Sample discovery
# ---------------------------------------------------------------------------


def discover_samples(
    directory: Path,
) -> list[tuple[Path, Path | None, str]]:
    """Discover sample .txt files with optional sidecar JSON files.

    Scans *directory* recursively for ``.txt`` files.  Each is paired
    with a sibling ``.expected.json`` sidecar if one exists.  Category
    is derived from the immediate subdirectory name; files directly in
    *directory* are categorized as ``"uncategorized"``.

    Args:
        directory: Root directory to search for samples.

    Returns:
        A sorted list of ``(txt_path, sidecar_path | None, category)``
        tuples, ordered by transcript file path.
    """
    base = Path(directory)
    results: list[tuple[Path, Path | None, str]] = []

    for txt_path in sorted(base.rglob("*.txt")):
        sidecar_path = txt_path.with_suffix(".expected.json")
        has_sidecar = sidecar_path.exists()

        # Derive category from parent directory relative to base.
        relative = txt_path.relative_to(base)
        category = relative.parts[0] if len(relative.parts) > 1 else "uncategorized"

        results.append(
            (
                txt_path,
                sidecar_path if has_sidecar else None,
                category,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Token extraction helpers
# ---------------------------------------------------------------------------


def _extract_token_counts(
    usage_metadata: list[Any],
) -> tuple[int, int, int]:
    """Extract token counts from a list of usage metadata objects.

    Sums ``prompt_token_count``, ``candidates_token_count``, and
    ``thoughts_token_count`` across all API attempts.

    Args:
        usage_metadata: List of usage objects from
            ``ExtractionResult.usage_metadata``.

    Returns:
        Tuple of ``(prompt_tokens, output_tokens, thoughts_tokens)``.
    """
    prompt = 0
    output = 0
    thoughts = 0

    for usage in usage_metadata:
        if usage is None:
            continue
        prompt += getattr(usage, "prompt_token_count", 0) or 0
        output += getattr(usage, "candidates_token_count", 0) or 0
        thoughts += getattr(usage, "thoughts_token_count", 0) or 0

    return prompt, output, thoughts


def _estimate_cost(prompt_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD from token counts.

    Uses Gemini 2.5 pricing: $1.25/1M input, $10.00/1M output.

    Args:
        prompt_tokens: Total prompt (input) tokens.
        output_tokens: Total output (candidates) tokens.

    Returns:
        Estimated cost in USD.
    """
    return (prompt_tokens * _PROMPT_COST_PER_1M + output_tokens * _OUTPUT_COST_PER_1M) / 1_000_000


# ---------------------------------------------------------------------------
# Main benchmark runner
# ---------------------------------------------------------------------------


def run_benchmark(
    directory: Path,
    output_path: Path,
    gemini_client: GeminiClient,
    *,
    delay_s: float = 4.0,
) -> BenchmarkResult:
    """Run the full benchmark suite against sample transcripts.

    Discovers samples, runs live Gemini extraction for each, scores
    samples that have sidecars, and collects latency/token metrics.

    Args:
        directory: Root directory containing sample transcripts.
        output_path: Directory for report output (used for JSONL history).
        gemini_client: An initialized GeminiClient for extraction.
        delay_s: Delay in seconds between API calls (rate limiting).
            Defaults to 4.0 (safe for 15 RPM free tier).

    Returns:
        A :class:`BenchmarkResult` with all per-sample and aggregate data.
    """
    samples = discover_samples(directory)
    total = len(samples)

    if total == 0:
        logger.warning("No samples found in %s", directory)
        return BenchmarkResult(timestamp=datetime.now().isoformat())

    result = BenchmarkResult(
        timestamp=datetime.now().isoformat(),
        model=gemini_client._model,
    )

    scored_samples: list[SampleScore] = []

    for idx, (txt_path, sidecar_path, category) in enumerate(samples, 1):
        sample_name = f"{category}/{txt_path.stem}"
        sr = SampleResult(
            sample_name=sample_name,
            category=category,
            txt_path=txt_path,
            has_sidecar=sidecar_path is not None,
        )

        # Load transcript text.
        transcript_text = txt_path.read_text(encoding="utf-8")

        # Load sidecar if available.
        sidecar: SidecarSpec | None = None
        if sidecar_path is not None:
            try:
                sidecar = load_sidecar(sidecar_path)
            except Exception as exc:
                logger.warning("Failed to load sidecar for %s: %s", sample_name, exc)
                sr.error = f"Sidecar load failed: {exc}"

        # Build calendar context from sidecar.
        calendar_context_text = ""
        owner_name = "Alice"
        reference_dt = datetime(2026, 2, 20, 10, 0, 0)

        if sidecar is not None:
            ctx = build_calendar_context(sidecar)
            calendar_context_text = ctx.events_text
            owner_name = sidecar.owner
            reference_dt = datetime.fromisoformat(sidecar.reference_datetime)

        # Rate limit: delay between API calls (skip before first).
        if idx > 1 and delay_s > 0:
            time.sleep(delay_s)

        # Run extraction with latency tracking.
        t0 = time.monotonic()
        try:
            extraction = gemini_client.extract_events(
                transcript_text=transcript_text,
                owner_name=owner_name,
                current_datetime=reference_dt,
                calendar_context=calendar_context_text,
            )
            sr.extraction = extraction
            sr.latency_s = time.monotonic() - t0

            # Extract token counts.
            prompt_t, output_t, thoughts_t = _extract_token_counts(extraction.usage_metadata)
            sr.prompt_tokens = prompt_t
            sr.output_tokens = output_t
            sr.thoughts_tokens = thoughts_t

        except Exception as exc:
            sr.latency_s = time.monotonic() - t0
            sr.error = str(exc)
            logger.error("Extraction failed for %s: %s", sample_name, exc)
            # Print progress with error.
            print(
                f"[{idx}/{total}] {sample_name}... ERROR ({sr.latency_s:.1f}s)",
                file=sys.stderr,
            )
            result.sample_results.append(sr)
            continue

        # Score if sidecar is available.
        if sidecar is not None and extraction is not None:
            try:
                score = score_sample(
                    actual_events=extraction.events,
                    expected_events=sidecar.expected_events,
                    tolerance_level=sidecar.tolerance,
                    sample_name=sample_name,
                    category=category,
                )
                sr.score = score
                scored_samples.append(score)

                # Print progress with score.
                print(
                    f"[{idx}/{total}] {sample_name}... "
                    f"P={score.precision:.2f} R={score.recall:.2f} "
                    f"({sr.latency_s:.1f}s)",
                    file=sys.stderr,
                )
            except Exception as exc:
                logger.error("Scoring failed for %s: %s", sample_name, exc)
                sr.error = f"Scoring failed: {exc}"
                print(
                    f"[{idx}/{total}] {sample_name}... SCORE_ERROR ({sr.latency_s:.1f}s)",
                    file=sys.stderr,
                )
        else:
            # No sidecar: extract only, warn.
            if sidecar is None:
                logger.warning("No sidecar for %s; skipping scoring", sample_name)
            print(
                f"[{idx}/{total}] {sample_name}... no sidecar ({sr.latency_s:.1f}s)",
                file=sys.stderr,
            )

        result.sample_results.append(sr)

    # Aggregate scores.
    result.aggregate = aggregate_scores(scored_samples)
    result.confidence_calibration = calibrate_confidence(scored_samples)

    # Sum totals.
    result.total_prompt_tokens = sum(sr.prompt_tokens for sr in result.sample_results)
    result.total_output_tokens = sum(sr.output_tokens for sr in result.sample_results)
    result.total_thoughts_tokens = sum(sr.thoughts_tokens for sr in result.sample_results)
    result.total_latency_s = sum(sr.latency_s for sr in result.sample_results)
    result.est_cost_usd = _estimate_cost(result.total_prompt_tokens, result.total_output_tokens)

    # Append JSONL history.
    _append_history(output_path, result)

    return result


# ---------------------------------------------------------------------------
# JSONL history
# ---------------------------------------------------------------------------


def _append_history(output_path: Path, result: BenchmarkResult) -> None:
    """Append one JSONL line per run to benchmark_history.jsonl.

    Creates the output directory if it does not exist.

    Args:
        output_path: Directory for reports.
        result: The benchmark result to record.
    """
    output_path.mkdir(parents=True, exist_ok=True)
    history_file = output_path / "benchmark_history.jsonl"

    agg = result.aggregate
    scored_count = agg.sample_count if agg else 0

    record = {
        "timestamp": result.timestamp,
        "model": result.model,
        "sample_count": len(result.sample_results),
        "scored_count": scored_count,
        "precision": round(agg.overall_precision, 4) if agg else None,
        "recall": round(agg.overall_recall, 4) if agg else None,
        "f1": round(agg.overall_f1, 4) if agg else None,
        "avg_latency_s": round(
            result.total_latency_s / max(len(result.sample_results), 1),
            2,
        ),
        "est_cost_usd": round(result.est_cost_usd, 6),
    }

    with open(history_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    logger.info("History appended to %s", history_file)
