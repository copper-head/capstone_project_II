"""Benchmark report formatters for console and markdown output.

Produces two output formats:
- **Console summary**: Compact table with overall and per-category P/R/F1,
  token usage, cost estimate, and confidence calibration.
- **Markdown report**: Detailed per-sample breakdown with expected vs actual
  event comparisons and mismatch details.

Follows the ``demo_output.py`` pattern of building a list of strings.
"""

from __future__ import annotations

from datetime import datetime

from cal_ai.benchmark.runner import BenchmarkResult, SampleResult
from cal_ai.benchmark.scoring import CategoryScore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BANNER_WIDTH = 60
_SEPARATOR = "=" * _BANNER_WIDTH


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------


def format_console_summary(result: BenchmarkResult) -> str:
    """Format a compact console summary of benchmark results.

    Includes overall P/R/F1, per-category breakdown, token usage,
    cost estimate, and confidence calibration stats.

    Args:
        result: The benchmark result to format.

    Returns:
        Multi-line string for console display.
    """
    lines: list[str] = []

    lines.append(_SEPARATOR)
    lines.append("  BENCHMARK RESULTS")
    lines.append(_SEPARATOR)

    agg = result.aggregate
    if agg is None or agg.sample_count == 0:
        lines.append("")
        lines.append("  No scored samples.")
        lines.append(_SEPARATOR)
        return "\n".join(lines)

    # Overall scores.
    lines.append("")
    lines.append("--- OVERALL ---")
    lines.append(f"  Samples scored: {agg.sample_count}")
    lines.append(
        f"  Precision: {agg.overall_precision:.4f}  "
        f"Recall: {agg.overall_recall:.4f}  "
        f"F1: {agg.overall_f1:.4f}"
    )
    lines.append(f"  TP: {agg.overall_tp}  FP: {agg.overall_fp}  FN: {agg.overall_fn}")

    # Per-category breakdown.
    if agg.per_category:
        lines.append("")
        lines.append("--- PER CATEGORY ---")
        for cat in agg.per_category:
            lines.append(_format_category_line(cat))

    # Confidence calibration.
    if result.confidence_calibration:
        lines.append("")
        lines.append("--- CONFIDENCE CALIBRATION ---")
        for level in ("high", "medium", "low"):
            if level in result.confidence_calibration:
                acc = result.confidence_calibration[level]
                lines.append(f"  {level}: {acc:.1%} accuracy")

    # Token usage and cost.
    lines.append("")
    lines.append("--- COST & LATENCY ---")
    lines.append(
        f"  Prompt tokens: {result.total_prompt_tokens:,}  "
        f"Output tokens: {result.total_output_tokens:,}"
    )
    if result.total_thoughts_tokens > 0:
        lines.append(f"  Thinking tokens: {result.total_thoughts_tokens:,}")
    lines.append(f"  Estimated cost: ${result.est_cost_usd:.4f}")
    n_samples = len(result.sample_results) or 1
    avg_latency = result.total_latency_s / n_samples
    lines.append(f"  Total latency: {result.total_latency_s:.1f}s  Avg: {avg_latency:.1f}s/sample")
    lines.append(f"  Model: {result.model}")

    lines.append(_SEPARATOR)
    return "\n".join(lines)


def _format_category_line(cat: CategoryScore) -> str:
    """Format a single category score as a console line.

    Args:
        cat: Category score to format.

    Returns:
        Formatted line like ``"  crud (14): P=0.95 R=0.90 F1=0.93"``.
    """
    return (
        f"  {cat.category} ({cat.sample_count}): "
        f"P={cat.precision:.2f} R={cat.recall:.2f} "
        f"F1={cat.f1:.2f}"
    )


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def format_markdown_report(result: BenchmarkResult) -> str:
    """Format a detailed markdown report of benchmark results.

    Includes overall summary, per-category table, per-sample detail
    with expected vs actual event comparisons and mismatch reasons.

    Args:
        result: The benchmark result to format.

    Returns:
        Markdown string ready to write to a file.
    """
    lines: list[str] = []

    lines.append(f"# Benchmark Report: {result.timestamp}")
    lines.append("")
    lines.append(f"**Model:** {result.model}")
    lines.append(f"**Samples:** {len(result.sample_results)} total")

    agg = result.aggregate
    if agg is None or agg.sample_count == 0:
        lines.append("")
        lines.append("No scored samples.")
        return "\n".join(lines)

    # Overall summary.
    lines.append(f"**Scored:** {agg.sample_count}")
    lines.append("")
    lines.append("## Overall Scores")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Precision | {agg.overall_precision:.4f} |")
    lines.append(f"| Recall | {agg.overall_recall:.4f} |")
    lines.append(f"| F1 | {agg.overall_f1:.4f} |")
    lines.append(f"| TP | {agg.overall_tp} |")
    lines.append(f"| FP | {agg.overall_fp} |")
    lines.append(f"| FN | {agg.overall_fn} |")

    # Per-category table.
    if agg.per_category:
        lines.append("")
        lines.append("## Per-Category Breakdown")
        lines.append("")
        lines.append("| Category | Samples | P | R | F1 | TP | FP | FN |")
        lines.append("|----------|---------|---|---|----|----|----|----|")
        for cat in agg.per_category:
            lines.append(
                f"| {cat.category} | {cat.sample_count} "
                f"| {cat.precision:.2f} | {cat.recall:.2f} "
                f"| {cat.f1:.2f} | {cat.tp} | {cat.fp} "
                f"| {cat.fn} |"
            )

    # Confidence calibration.
    if result.confidence_calibration:
        lines.append("")
        lines.append("## Confidence Calibration")
        lines.append("")
        lines.append("| Level | Accuracy |")
        lines.append("|-------|----------|")
        for level in ("high", "medium", "low"):
            if level in result.confidence_calibration:
                acc = result.confidence_calibration[level]
                lines.append(f"| {level} | {acc:.1%} |")

    # Cost and latency.
    lines.append("")
    lines.append("## Cost & Latency")
    lines.append("")
    lines.append(f"- Prompt tokens: {result.total_prompt_tokens:,}")
    lines.append(f"- Output tokens: {result.total_output_tokens:,}")
    if result.total_thoughts_tokens > 0:
        lines.append(f"- Thinking tokens: {result.total_thoughts_tokens:,}")
    lines.append(f"- Estimated cost: ${result.est_cost_usd:.4f}")
    n_samples = len(result.sample_results) or 1
    avg_latency = result.total_latency_s / n_samples
    lines.append(f"- Total latency: {result.total_latency_s:.1f}s")
    lines.append(f"- Average latency: {avg_latency:.1f}s/sample")

    # Per-sample details.
    lines.append("")
    lines.append("## Per-Sample Details")

    for sr in result.sample_results:
        lines.append("")
        _append_sample_detail(lines, sr)

    # AI summary section.
    if result.ai_summary:
        lines.append("")
        lines.append("## AI Self-Evaluation")
        lines.append("")
        lines.append(result.ai_summary)
        if result.summary_prompt_tokens or result.summary_output_tokens:
            lines.append("")
            lines.append(
                f"*Summary generation: "
                f"{result.summary_prompt_tokens:,} prompt tokens, "
                f"{result.summary_output_tokens:,} output tokens*"
            )

    lines.append("")
    return "\n".join(lines)


def _append_sample_detail(lines: list[str], sr: SampleResult) -> None:
    """Append detailed markdown for a single sample result.

    Args:
        lines: List to append to.
        sr: The sample result.
    """
    lines.append(f"### {sr.sample_name}")
    lines.append("")

    if sr.error:
        lines.append(f"**Error:** {sr.error}")
        lines.append("")
        return

    lines.append(f"- Latency: {sr.latency_s:.1f}s")
    lines.append(f"- Tokens: {sr.prompt_tokens} prompt, {sr.output_tokens} output")

    if sr.score is not None:
        score = sr.score
        lines.append(f"- Tolerance: {score.tolerance}")
        lines.append(
            f"- P={score.precision:.2f} R={score.recall:.2f} "
            f"F1={score.f1:.2f} "
            f"(TP={score.tp} FP={score.fp} FN={score.fn})"
        )

        # Per-event detail.
        if score.per_event_details:
            lines.append("")
            lines.append("**Event Details:**")
            lines.append("")
            for detail in score.per_event_details:
                cls = detail.classification.upper()
                if detail.actual_event and detail.expected_event:
                    lines.append(
                        f"- [{cls}] Actual: "
                        f"`{detail.actual_event.action}` "
                        f'"{detail.actual_event.title}" '
                        f"@ {detail.actual_event.start_time}"
                    )
                    lines.append(
                        f"  Expected: "
                        f"`{detail.expected_event.action}` "
                        f'"{detail.expected_event.title}" '
                        f"@ {detail.expected_event.start_time}"
                    )
                    if detail.mismatch_reasons:
                        for reason in detail.mismatch_reasons:
                            lines.append(f"  - {reason}")
                elif detail.actual_event:
                    lines.append(
                        f"- [{cls}] Actual only: "
                        f"`{detail.actual_event.action}` "
                        f'"{detail.actual_event.title}" '
                        f"@ {detail.actual_event.start_time}"
                    )
                elif detail.expected_event:
                    lines.append(
                        f"- [{cls}] Expected only: "
                        f"`{detail.expected_event.action}` "
                        f'"{detail.expected_event.title}" '
                        f"@ {detail.expected_event.start_time}"
                    )
    elif not sr.has_sidecar:
        lines.append("- *No sidecar -- scoring skipped*")

    # Show extracted events count.
    if sr.extraction:
        n_events = len(sr.extraction.events)
        lines.append(f"- Events extracted: {n_events}")


def generate_report_filename() -> str:
    """Generate a timestamped report filename.

    Returns:
        Filename like ``"benchmark_2026-02-20T14-30-45.md"``.
    """
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    return f"benchmark_{ts}.md"
