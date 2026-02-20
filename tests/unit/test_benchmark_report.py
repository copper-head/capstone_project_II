"""Unit tests for the benchmark report module.

Tests cover: console summary formatting, markdown report formatting,
report filename generation, and edge cases (empty results, single
sample, multiple categories).
"""

from __future__ import annotations

from pathlib import Path

from cal_ai.benchmark.report import (
    format_console_summary,
    format_markdown_report,
    generate_report_filename,
)
from cal_ai.benchmark.runner import BenchmarkResult, SampleResult
from cal_ai.benchmark.scoring import (
    AggregateScore,
    CategoryScore,
    EventMatchDetail,
    SampleScore,
)
from cal_ai.models.extraction import ExtractedEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sample_score(
    *,
    name: str = "crud/test",
    category: str = "crud",
    tp: int = 1,
    fp: int = 0,
    fn: int = 0,
    precision: float = 1.0,
    recall: float = 1.0,
    f1: float = 1.0,
    tolerance: str = "moderate",
) -> SampleScore:
    """Create a minimal SampleScore for testing."""
    return SampleScore(
        sample_name=name,
        category=category,
        tolerance=tolerance,
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def _make_benchmark_result(
    *,
    sample_results: list[SampleResult] | None = None,
    aggregate: AggregateScore | None = None,
) -> BenchmarkResult:
    """Create a BenchmarkResult for testing."""
    return BenchmarkResult(
        sample_results=sample_results or [],
        aggregate=aggregate,
        confidence_calibration={},
        total_prompt_tokens=1000,
        total_output_tokens=200,
        total_thoughts_tokens=0,
        total_latency_s=10.0,
        est_cost_usd=0.0033,
        model="gemini-2.5-pro",
        timestamp="2026-02-20T14:30:00",
    )


def _make_sample_result(
    *,
    name: str = "crud/test",
    category: str = "crud",
    score: SampleScore | None = None,
    latency_s: float = 2.5,
) -> SampleResult:
    """Create a minimal SampleResult for testing."""
    return SampleResult(
        sample_name=name,
        category=category,
        txt_path=Path(f"samples/{category}/{name.split('/')[-1]}.txt"),
        has_sidecar=score is not None,
        score=score,
        latency_s=latency_s,
        prompt_tokens=500,
        output_tokens=100,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFormatConsoleSummary:
    """Tests for format_console_summary."""

    def test_empty_result_shows_no_scored(self) -> None:
        """Empty result shows 'No scored samples'."""
        result = _make_benchmark_result()
        output = format_console_summary(result)
        assert "No scored samples" in output

    def test_with_aggregate_shows_overall(self) -> None:
        """Result with aggregate shows overall P/R/F1."""
        agg = AggregateScore(
            overall_tp=10,
            overall_fp=2,
            overall_fn=1,
            overall_precision=0.8333,
            overall_recall=0.9091,
            overall_f1=0.8696,
            sample_count=5,
        )
        result = _make_benchmark_result(aggregate=agg)
        output = format_console_summary(result)

        assert "BENCHMARK RESULTS" in output
        assert "Precision: 0.8333" in output
        assert "Recall: 0.9091" in output
        assert "F1: 0.8696" in output
        assert "Samples scored: 5" in output

    def test_with_categories_shows_breakdown(self) -> None:
        """Result with per-category scores shows category lines."""
        agg = AggregateScore(
            overall_tp=10,
            overall_fp=2,
            overall_fn=1,
            overall_precision=0.83,
            overall_recall=0.91,
            overall_f1=0.87,
            per_category=[
                CategoryScore(
                    category="crud",
                    tp=8,
                    fp=1,
                    fn=0,
                    precision=0.89,
                    recall=1.0,
                    f1=0.94,
                    sample_count=3,
                ),
                CategoryScore(
                    category="adversarial",
                    tp=2,
                    fp=1,
                    fn=1,
                    precision=0.67,
                    recall=0.67,
                    f1=0.67,
                    sample_count=2,
                ),
            ],
            sample_count=5,
        )
        result = _make_benchmark_result(aggregate=agg)
        output = format_console_summary(result)

        assert "PER CATEGORY" in output
        assert "crud (3)" in output
        assert "adversarial (2)" in output

    def test_shows_cost_and_latency(self) -> None:
        """Result shows cost and latency information."""
        agg = AggregateScore(
            overall_tp=1,
            overall_fp=0,
            overall_fn=0,
            overall_precision=1.0,
            overall_recall=1.0,
            overall_f1=1.0,
            sample_count=1,
        )
        result = _make_benchmark_result(aggregate=agg)
        output = format_console_summary(result)

        assert "Prompt tokens: 1,000" in output
        assert "Output tokens: 200" in output
        assert "Estimated cost: $0.0033" in output
        assert "gemini-2.5-pro" in output

    def test_with_confidence_calibration(self) -> None:
        """Result with confidence calibration shows accuracy."""
        agg = AggregateScore(
            overall_tp=1,
            overall_fp=0,
            overall_fn=0,
            overall_precision=1.0,
            overall_recall=1.0,
            overall_f1=1.0,
            sample_count=1,
        )
        result = _make_benchmark_result(aggregate=agg)
        result.confidence_calibration = {
            "high": 0.95,
            "medium": 0.70,
        }
        output = format_console_summary(result)

        assert "CONFIDENCE CALIBRATION" in output
        assert "high: 95.0% accuracy" in output
        assert "medium: 70.0% accuracy" in output

    def test_shows_thinking_tokens_when_present(self) -> None:
        """Thinking tokens line appears only when nonzero."""
        agg = AggregateScore(
            overall_tp=1,
            overall_fp=0,
            overall_fn=0,
            overall_precision=1.0,
            overall_recall=1.0,
            overall_f1=1.0,
            sample_count=1,
        )
        result = _make_benchmark_result(aggregate=agg)
        result.total_thoughts_tokens = 5000
        output = format_console_summary(result)

        assert "Thinking tokens: 5,000" in output


class TestFormatMarkdownReport:
    """Tests for format_markdown_report."""

    def test_empty_result_shows_no_scored(self) -> None:
        """Empty result shows 'No scored samples'."""
        result = _make_benchmark_result()
        output = format_markdown_report(result)
        assert "No scored samples" in output

    def test_with_aggregate_shows_table(self) -> None:
        """Result with aggregate shows markdown table."""
        agg = AggregateScore(
            overall_tp=5,
            overall_fp=1,
            overall_fn=0,
            overall_precision=0.8333,
            overall_recall=1.0,
            overall_f1=0.9091,
            sample_count=3,
        )
        score = _make_sample_score(tp=2, fp=0, fn=0, precision=1.0, recall=1.0, f1=1.0)
        sr = _make_sample_result(score=score)
        result = _make_benchmark_result(
            sample_results=[sr],
            aggregate=agg,
        )
        output = format_markdown_report(result)

        assert "# Benchmark Report" in output
        assert "## Overall Scores" in output
        assert "| Precision | 0.8333 |" in output
        assert "## Per-Sample Details" in output
        assert "### crud/test" in output

    def test_per_sample_detail_with_score(self) -> None:
        """Sample with score shows P/R/F1 in detail."""
        agg = AggregateScore(
            overall_tp=1,
            overall_fp=0,
            overall_fn=0,
            overall_precision=1.0,
            overall_recall=1.0,
            overall_f1=1.0,
            sample_count=1,
        )
        score = _make_sample_score()
        sr = _make_sample_result(score=score)
        result = _make_benchmark_result(sample_results=[sr], aggregate=agg)
        output = format_markdown_report(result)

        assert "P=1.00 R=1.00 F1=1.00" in output
        assert "Tolerance: moderate" in output

    def test_per_sample_detail_no_sidecar(self) -> None:
        """Sample without sidecar shows scoring skipped note."""
        agg = AggregateScore(
            overall_tp=0,
            overall_fp=0,
            overall_fn=0,
            overall_precision=1.0,
            overall_recall=1.0,
            overall_f1=1.0,
            sample_count=0,
        )
        sr = _make_sample_result(score=None)
        # Override to not have sidecar.
        sr.has_sidecar = False
        result = _make_benchmark_result(sample_results=[sr], aggregate=agg)
        # Need at least 1 sample_count to avoid "No scored samples" path
        result.aggregate = AggregateScore(
            overall_tp=0,
            overall_fp=0,
            overall_fn=0,
            overall_precision=1.0,
            overall_recall=1.0,
            overall_f1=1.0,
            sample_count=1,
        )
        output = format_markdown_report(result)

        assert "No sidecar" in output

    def test_per_sample_error(self) -> None:
        """Sample with error shows error message."""
        agg = AggregateScore(
            overall_tp=0,
            overall_fp=0,
            overall_fn=0,
            overall_precision=1.0,
            overall_recall=1.0,
            overall_f1=1.0,
            sample_count=1,
        )
        sr = _make_sample_result()
        sr.error = "Gemini API failed"
        result = _make_benchmark_result(sample_results=[sr], aggregate=agg)
        output = format_markdown_report(result)

        assert "**Error:** Gemini API failed" in output

    def test_with_event_match_details(self) -> None:
        """Sample with event match details shows actual vs expected."""
        actual_event = ExtractedEvent(
            title="Team Meeting",
            start_time="2026-02-21T10:00:00",
            confidence="high",
            reasoning="test",
            action="create",
        )
        expected_event_data = {
            "action": "create",
            "title": "Team Meeting",
            "start_time": "2026-02-21T10:00:00",
        }
        from tests.regression.schema import SidecarExpectedEvent

        expected_event = SidecarExpectedEvent.model_validate(expected_event_data)

        score = SampleScore(
            sample_name="crud/test",
            category="crud",
            tolerance="moderate",
            tp=1,
            fp=0,
            fn=0,
            precision=1.0,
            recall=1.0,
            f1=1.0,
            per_event_details=[
                EventMatchDetail(
                    classification="tp",
                    actual_event=actual_event,
                    expected_event=expected_event,
                ),
            ],
        )
        sr = _make_sample_result(score=score)
        agg = AggregateScore(
            overall_tp=1,
            overall_fp=0,
            overall_fn=0,
            overall_precision=1.0,
            overall_recall=1.0,
            overall_f1=1.0,
            sample_count=1,
        )
        result = _make_benchmark_result(sample_results=[sr], aggregate=agg)
        output = format_markdown_report(result)

        assert "[TP]" in output
        assert "Team Meeting" in output

    def test_ai_summary_section_included(self) -> None:
        """Markdown report includes AI summary when present."""
        agg = AggregateScore(
            overall_tp=1,
            overall_fp=0,
            overall_fn=0,
            overall_precision=1.0,
            overall_recall=1.0,
            overall_f1=1.0,
            sample_count=1,
        )
        result = _make_benchmark_result(aggregate=agg)
        result.ai_summary = "The pipeline shows excellent performance."
        result.summary_prompt_tokens = 300
        result.summary_output_tokens = 150
        output = format_markdown_report(result)

        assert "## AI Self-Evaluation" in output
        assert "The pipeline shows excellent performance." in output
        assert "300 prompt tokens" in output
        assert "150 output tokens" in output

    def test_ai_summary_section_absent_when_empty(self) -> None:
        """Markdown report omits AI summary when empty."""
        agg = AggregateScore(
            overall_tp=1,
            overall_fp=0,
            overall_fn=0,
            overall_precision=1.0,
            overall_recall=1.0,
            overall_f1=1.0,
            sample_count=1,
        )
        result = _make_benchmark_result(aggregate=agg)
        result.ai_summary = ""
        output = format_markdown_report(result)

        assert "AI Self-Evaluation" not in output


class TestGenerateReportFilename:
    """Tests for generate_report_filename."""

    def test_filename_format(self) -> None:
        """Filename starts with 'benchmark_' and ends with '.md'."""
        filename = generate_report_filename()
        assert filename.startswith("benchmark_")
        assert filename.endswith(".md")

    def test_filename_contains_timestamp(self) -> None:
        """Filename contains a timestamp-like pattern."""
        filename = generate_report_filename()
        # Should have pattern like 2026-02-20T14-30-45
        parts = filename.replace("benchmark_", "").replace(".md", "")
        assert "T" in parts
        assert len(parts) == 19  # YYYY-MM-DDTHH-MM-SS
