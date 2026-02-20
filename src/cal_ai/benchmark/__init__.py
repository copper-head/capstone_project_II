"""Benchmark suite for scoring extraction pipeline accuracy.

Provides Precision/Recall/F1 metrics, confidence calibration, event
matching using the regression test tolerance engine, runner for live
Gemini extraction, report formatters for console and markdown output,
and AI-generated self-evaluation summaries.
"""

from __future__ import annotations

from cal_ai.benchmark.report import (
    format_console_summary,
    format_markdown_report,
    generate_report_filename,
)
from cal_ai.benchmark.runner import (
    BenchmarkResult,
    SampleResult,
    discover_samples,
    run_benchmark,
)
from cal_ai.benchmark.scoring import (
    AggregateScore,
    EventMatchDetail,
    SampleScore,
    aggregate_scores,
    calibrate_confidence,
    score_sample,
)
from cal_ai.benchmark.summary import generate_ai_summary

__all__ = [
    "AggregateScore",
    "BenchmarkResult",
    "EventMatchDetail",
    "SampleResult",
    "SampleScore",
    "aggregate_scores",
    "calibrate_confidence",
    "discover_samples",
    "format_console_summary",
    "format_markdown_report",
    "generate_ai_summary",
    "generate_report_filename",
    "run_benchmark",
    "score_sample",
]
