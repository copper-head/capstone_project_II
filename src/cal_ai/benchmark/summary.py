"""AI-generated summary for benchmark reports.

Uses Gemini to self-evaluate benchmark results, identifying strengths,
failure patterns, and suggesting improvements.  Follows LLM-as-a-judge
best practice with structured criteria and CoT reasoning.

Functions:
    :func:`generate_ai_summary` -- produce a markdown summary section.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cal_ai.benchmark.runner import BenchmarkResult
    from cal_ai.llm import GeminiClient

logger = logging.getLogger(__name__)


def _build_summary_prompt(result: BenchmarkResult) -> str:
    """Build a structured prompt for Gemini self-evaluation.

    Keeps the prompt under ~2000 tokens by including only aggregate
    stats, per-category breakdown, and the bottom 5 samples by F1.

    Args:
        result: The benchmark result to summarize.

    Returns:
        The prompt string for the AI summary call.
    """
    lines: list[str] = []

    lines.append(
        "You are evaluating the performance of an AI calendar-event "
        "extraction pipeline. Analyze the benchmark results below and "
        "provide a structured self-evaluation."
    )
    lines.append("")

    # Overall metrics.
    agg = result.aggregate
    if agg is not None and agg.sample_count > 0:
        lines.append("## Overall Metrics")
        lines.append(
            f"- Precision: {agg.overall_precision:.4f}"
        )
        lines.append(f"- Recall: {agg.overall_recall:.4f}")
        lines.append(f"- F1: {agg.overall_f1:.4f}")
        lines.append(
            f"- TP: {agg.overall_tp}  FP: {agg.overall_fp}  "
            f"FN: {agg.overall_fn}"
        )
        lines.append(
            f"- Samples scored: {agg.sample_count}"
        )
        lines.append("")

        # Per-category breakdown.
        if agg.per_category:
            lines.append("## Per-Category Breakdown")
            for cat in agg.per_category:
                lines.append(
                    f"- {cat.category} ({cat.sample_count} samples): "
                    f"P={cat.precision:.2f} R={cat.recall:.2f} "
                    f"F1={cat.f1:.2f} "
                    f"(TP={cat.tp} FP={cat.fp} FN={cat.fn})"
                )
            lines.append("")

    # Worst-performing samples (bottom 5 by F1).
    scored = [
        sr for sr in result.sample_results
        if sr.score is not None
    ]
    if scored:
        scored_sorted = sorted(scored, key=lambda s: s.score.f1)
        bottom = scored_sorted[:5]
        lines.append("## Worst-Performing Samples (Bottom 5 by F1)")
        for sr in bottom:
            sc = sr.score
            lines.append(
                f"- {sr.sample_name}: F1={sc.f1:.2f} "
                f"(P={sc.precision:.2f} R={sc.recall:.2f}, "
                f"TP={sc.tp} FP={sc.fp} FN={sc.fn}, "
                f"tolerance={sc.tolerance})"
            )
            # Include mismatch reasons for failing events.
            for detail in sc.per_event_details:
                if detail.mismatch_reasons:
                    for reason in detail.mismatch_reasons:
                        lines.append(f"  - {reason}")
        lines.append("")

    # Confidence calibration.
    if result.confidence_calibration:
        lines.append("## Confidence Calibration")
        for level in ("high", "medium", "low"):
            if level in result.confidence_calibration:
                acc = result.confidence_calibration[level]
                lines.append(f"- {level}: {acc:.1%} accuracy")
        lines.append("")

    # Cost info.
    lines.append("## Cost")
    lines.append(
        f"- Prompt tokens: {result.total_prompt_tokens:,}"
    )
    lines.append(
        f"- Output tokens: {result.total_output_tokens:,}"
    )
    lines.append(
        f"- Estimated cost: ${result.est_cost_usd:.4f}"
    )
    lines.append("")

    # Instructions.
    lines.append("## Your Task")
    lines.append("")
    lines.append(
        "Evaluate these results criterion by criterion. For each, "
        "provide a brief assessment (1-2 sentences):"
    )
    lines.append("")
    lines.append(
        "1. **Overall Quality**: Is the F1 score acceptable for a "
        "production calendar assistant? What does the P/R balance "
        "tell us?"
    )
    lines.append(
        "2. **Category Weaknesses**: Which categories need the most "
        "improvement? Why might they be harder?"
    )
    lines.append(
        "3. **Failure Patterns**: What common failure patterns do "
        "you see in the worst-performing samples?"
    )
    lines.append(
        "4. **Confidence Calibration**: Is the model well-calibrated "
        "(high confidence = high accuracy)?"
    )
    lines.append(
        "5. **Actionable Improvements**: Suggest 2-3 specific, "
        "actionable improvements to the extraction prompt or "
        "pipeline that would address the identified weaknesses."
    )
    lines.append("")
    lines.append(
        "Keep your response concise (under 500 words). Use markdown "
        "headers for each criterion."
    )

    return "\n".join(lines)


def generate_ai_summary(
    result: BenchmarkResult,
    gemini_client: GeminiClient,
) -> str:
    """Generate an AI summary of benchmark results via Gemini.

    Composes a structured prompt from the benchmark metrics and asks
    Gemini to self-evaluate: what went well, failure patterns, and
    suggested improvements.

    The summary call's token cost is tracked and returned so the caller
    can include it in total cost accounting.

    Args:
        result: The completed benchmark result to summarize.
        gemini_client: An initialized GeminiClient for the summary call.

    Returns:
        A markdown string containing the AI-generated summary.  On
        failure, returns a note like
        ``"AI summary unavailable: <error>"``.
    """
    from google.genai import types as genai_types

    prompt = _build_summary_prompt(result)

    logger.debug("AI summary prompt:\n%s", prompt)

    config = genai_types.GenerateContentConfig(
        system_instruction=(
            "You are an expert AI evaluator analyzing the performance "
            "of a calendar-event extraction pipeline. Be specific and "
            "data-driven in your analysis."
        ),
    )

    try:
        call_result = gemini_client._call_api(prompt, config)
        summary_text = call_result.text

        # Track the summary call's token usage.
        if call_result.usage is not None:
            prompt_tokens = (
                getattr(call_result.usage, "prompt_token_count", 0) or 0
            )
            output_tokens = (
                getattr(
                    call_result.usage, "candidates_token_count", 0
                )
                or 0
            )
            result.summary_prompt_tokens = prompt_tokens
            result.summary_output_tokens = output_tokens

            # Add to totals for cost tracking.
            result.total_prompt_tokens += prompt_tokens
            result.total_output_tokens += output_tokens

            # Recalculate cost.
            from cal_ai.benchmark.runner import _estimate_cost

            result.est_cost_usd = _estimate_cost(
                result.total_prompt_tokens,
                result.total_output_tokens,
            )

        logger.info("AI summary generated successfully")
        return summary_text

    except Exception as exc:
        logger.warning("AI summary generation failed: %s", exc)
        return f"AI summary unavailable: {exc}"
