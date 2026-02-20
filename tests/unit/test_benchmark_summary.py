"""Unit tests for the benchmark AI summary module.

Covers: prompt construction, successful summary generation, graceful
failure on API error, and cost tracking integration.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from cal_ai.benchmark.runner import BenchmarkResult, SampleResult
from cal_ai.benchmark.scoring import (
    AggregateScore,
    CategoryScore,
    EventMatchDetail,
    SampleScore,
)
from cal_ai.benchmark.summary import (
    _build_summary_prompt,
    generate_ai_summary,
)

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
    tolerance: str = "moderate",
    f1: float = 1.0,
    per_event_details: list[EventMatchDetail] | None = None,
) -> SampleScore:
    """Create a minimal SampleScore for testing."""
    p = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    return SampleScore(
        sample_name=name,
        category=category,
        tolerance=tolerance,
        tp=tp,
        fp=fp,
        fn=fn,
        precision=p,
        recall=r,
        f1=f1,
        per_event_details=per_event_details or [],
    )


def _make_sample_result(
    *,
    name: str = "crud/test",
    category: str = "crud",
    score: SampleScore | None = None,
) -> SampleResult:
    """Create a minimal SampleResult."""
    return SampleResult(
        sample_name=name,
        category=category,
        txt_path=Path(f"samples/{category}/{name.split('/')[-1]}.txt"),
        has_sidecar=score is not None,
        score=score,
        latency_s=2.0,
        prompt_tokens=500,
        output_tokens=100,
    )


def _make_benchmark_result(
    *,
    sample_results: list[SampleResult] | None = None,
    aggregate: AggregateScore | None = None,
    confidence_calibration: dict[str, float] | None = None,
) -> BenchmarkResult:
    """Create a BenchmarkResult for testing."""
    return BenchmarkResult(
        sample_results=sample_results or [],
        aggregate=aggregate,
        confidence_calibration=confidence_calibration or {},
        total_prompt_tokens=1000,
        total_output_tokens=200,
        total_thoughts_tokens=0,
        total_latency_s=10.0,
        est_cost_usd=0.0033,
        model="gemini-2.5-pro",
        timestamp="2026-02-20T14:30:00",
    )


def _make_mock_gemini_client(
    response_text: str = "AI summary content here.",
    prompt_tokens: int = 500,
    output_tokens: int = 200,
) -> MagicMock:
    """Create a mock GeminiClient that returns a fixed LLMCallResult."""
    from cal_ai.llm import LLMCallResult

    usage = MagicMock()
    usage.prompt_token_count = prompt_tokens
    usage.candidates_token_count = output_tokens

    call_result = LLMCallResult(text=response_text, usage=usage)

    client = MagicMock()
    client._call_api.return_value = call_result
    return client


# ---------------------------------------------------------------------------
# Tests: _build_summary_prompt
# ---------------------------------------------------------------------------


class TestBuildSummaryPrompt:
    """Tests for the prompt construction function."""

    def test_includes_overall_metrics(self) -> None:
        """Prompt includes overall P/R/F1 when aggregate is present."""
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
        prompt = _build_summary_prompt(result)

        assert "Precision: 0.8333" in prompt
        assert "Recall: 0.9091" in prompt
        assert "F1: 0.8696" in prompt
        assert "Samples scored: 5" in prompt

    def test_includes_per_category_breakdown(self) -> None:
        """Prompt includes per-category breakdown."""
        agg = AggregateScore(
            overall_tp=5,
            overall_fp=1,
            overall_fn=0,
            overall_precision=0.83,
            overall_recall=1.0,
            overall_f1=0.91,
            per_category=[
                CategoryScore(
                    category="crud",
                    tp=4,
                    fp=0,
                    fn=0,
                    precision=1.0,
                    recall=1.0,
                    f1=1.0,
                    sample_count=3,
                ),
            ],
            sample_count=3,
        )
        result = _make_benchmark_result(aggregate=agg)
        prompt = _build_summary_prompt(result)

        assert "Per-Category Breakdown" in prompt
        assert "crud (3 samples)" in prompt

    def test_includes_worst_performing_samples(self) -> None:
        """Prompt includes bottom 5 samples by F1."""
        score_good = _make_sample_score(name="crud/good", f1=1.0, tp=1)
        score_bad = _make_sample_score(
            name="adversarial/bad",
            category="adversarial",
            f1=0.0,
            tp=0,
            fp=1,
            fn=1,
        )
        sr_good = _make_sample_result(name="crud/good", score=score_good)
        sr_bad = _make_sample_result(
            name="adversarial/bad",
            category="adversarial",
            score=score_bad,
        )
        agg = AggregateScore(
            overall_tp=1,
            overall_fp=1,
            overall_fn=1,
            overall_precision=0.5,
            overall_recall=0.5,
            overall_f1=0.5,
            sample_count=2,
        )
        result = _make_benchmark_result(
            sample_results=[sr_good, sr_bad],
            aggregate=agg,
        )
        prompt = _build_summary_prompt(result)

        assert "Worst-Performing Samples" in prompt
        assert "adversarial/bad" in prompt

    def test_includes_confidence_calibration(self) -> None:
        """Prompt includes confidence calibration when present."""
        agg = AggregateScore(
            overall_tp=1,
            overall_fp=0,
            overall_fn=0,
            overall_precision=1.0,
            overall_recall=1.0,
            overall_f1=1.0,
            sample_count=1,
        )
        result = _make_benchmark_result(
            aggregate=agg,
            confidence_calibration={"high": 0.95, "medium": 0.7},
        )
        prompt = _build_summary_prompt(result)

        assert "Confidence Calibration" in prompt
        assert "high: 95.0% accuracy" in prompt
        assert "medium: 70.0% accuracy" in prompt

    def test_includes_evaluation_criteria(self) -> None:
        """Prompt includes the five evaluation criteria."""
        result = _make_benchmark_result()
        prompt = _build_summary_prompt(result)

        assert "Overall Quality" in prompt
        assert "Category Weaknesses" in prompt
        assert "Failure Patterns" in prompt
        assert "Confidence Calibration" in prompt
        assert "Actionable Improvements" in prompt

    def test_includes_cost_info(self) -> None:
        """Prompt includes cost information."""
        result = _make_benchmark_result()
        prompt = _build_summary_prompt(result)

        assert "Prompt tokens: 1,000" in prompt
        assert "Output tokens: 200" in prompt
        assert "$0.0033" in prompt


# ---------------------------------------------------------------------------
# Tests: generate_ai_summary
# ---------------------------------------------------------------------------


class TestGenerateAiSummary:
    """Tests for the AI summary generation function."""

    def test_returns_summary_text(self) -> None:
        """Successful call returns the summary text."""
        client = _make_mock_gemini_client(response_text="The pipeline shows strong performance.")
        result = _make_benchmark_result()
        summary = generate_ai_summary(result, client)

        assert "strong performance" in summary
        client._call_api.assert_called_once()

    def test_tracks_summary_token_usage(self) -> None:
        """Summary call's token usage is tracked on the result."""
        client = _make_mock_gemini_client(prompt_tokens=300, output_tokens=150)
        result = _make_benchmark_result()
        original_prompt = result.total_prompt_tokens
        original_output = result.total_output_tokens

        generate_ai_summary(result, client)

        assert result.summary_prompt_tokens == 300
        assert result.summary_output_tokens == 150
        assert result.total_prompt_tokens == original_prompt + 300
        assert result.total_output_tokens == original_output + 150

    def test_recalculates_cost(self) -> None:
        """Summary call updates the estimated cost."""
        client = _make_mock_gemini_client(prompt_tokens=1000, output_tokens=500)
        result = _make_benchmark_result()
        original_cost = result.est_cost_usd

        generate_ai_summary(result, client)

        # Cost should have increased.
        assert result.est_cost_usd > original_cost

    def test_graceful_failure_on_api_error(self) -> None:
        """API error returns a graceful failure message."""
        client = MagicMock()
        client._call_api.side_effect = Exception("API rate limit")

        result = _make_benchmark_result()
        summary = generate_ai_summary(result, client)

        assert "AI summary unavailable" in summary
        assert "API rate limit" in summary

    def test_graceful_failure_preserves_report(self) -> None:
        """On failure, token counts remain unchanged."""
        client = MagicMock()
        client._call_api.side_effect = RuntimeError("Network error")

        result = _make_benchmark_result()
        original_tokens = result.total_prompt_tokens

        generate_ai_summary(result, client)

        # Token counts unchanged on failure.
        assert result.total_prompt_tokens == original_tokens

    def test_handles_none_usage(self) -> None:
        """Summary works when usage metadata is None."""
        from cal_ai.llm import LLMCallResult

        call_result = LLMCallResult(text="Summary text.", usage=None)
        client = MagicMock()
        client._call_api.return_value = call_result

        result = _make_benchmark_result()
        summary = generate_ai_summary(result, client)

        assert summary == "Summary text."
        assert result.summary_prompt_tokens == 0
        assert result.summary_output_tokens == 0
