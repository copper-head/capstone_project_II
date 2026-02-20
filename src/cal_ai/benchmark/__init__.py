"""Benchmark suite for scoring extraction pipeline accuracy.

Provides Precision/Recall/F1 metrics, confidence calibration, and
event matching using the regression test tolerance engine.
"""

from __future__ import annotations

from cal_ai.benchmark.scoring import (
    AggregateScore,
    EventMatchDetail,
    SampleScore,
    aggregate_scores,
    calibrate_confidence,
    score_sample,
)

__all__ = [
    "AggregateScore",
    "EventMatchDetail",
    "SampleScore",
    "aggregate_scores",
    "calibrate_confidence",
    "score_sample",
]
