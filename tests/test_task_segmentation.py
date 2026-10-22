"""
Phase 3 Tests — Task Segmentation Engine.

Verifies:
  - Empty trace → UNKNOWN autonomy with zero tasks
  - Single autonomous span → AUTONOMOUS task
  - Explicit human intervention span → HUMAN_EXPLICIT task
  - Inferred heuristic intervention span → HUMAN_INFERRED task
  - Large gap between spans → UNKNOWN gap task inserted
  - Mixed trace (autonomous + explicit + gap) → correct counts
  - Autonomy bounds arithmetic correctness
  - Aggregate across multiple traces
  - Determinism (same input → same output every call)
  - to_dict() serialization roundtrip
"""

import pytest
from datetime import datetime, timedelta
from app.analysis.task_segmentation import (
    TaskOutcome,
    TraceSegmentationResult,
    aggregate_autonomy_across_traces,
    segment_trace,
)
from app.epistemic.tags import EpistemicTag, TrustLevel
from app.ingestion.schema import NormalizedSpan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_span(
    span_id: str,
    name: str,
    start_offset_s: float,
    duration_s: float,
    trace_id: str = "trace-001",
    is_human: bool = False,
    detection: str = "OBSERVED_TELEMETRY",
    human_action: str = None,
    status_code: str = "OK",
    input_tokens: int = None,
    output_tokens: int = None,
    provider: str = None,
    cost_usd: float = 0.0,
    trust_level: TrustLevel = TrustLevel.T1,
) -> NormalizedSpan:
    base = datetime(2026, 1, 1, 0, 0, 0)
    start = base + timedelta(seconds=start_offset_s)
    end   = base + timedelta(seconds=start_offset_s + duration_s)
    return NormalizedSpan(
        span_id=span_id,
        trace_id=trace_id,
        name=name,
        span_kind="INTERNAL",
        start_time=start,
        end_time=end,
        duration_ms=duration_s * 1000.0,
        status_code=status_code,
        is_human_intervention=is_human,
        human_action_type=human_action,
        intervention_detection_method=detection if is_human else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        has_token_data=(input_tokens is not None or output_tokens is not None),
        provider_name=provider,
        cost_usd=cost_usd,
        cost_status="MEASURED",
        trust_level=trust_level,
    )


# ---------------------------------------------------------------------------
# Test: empty trace
# ---------------------------------------------------------------------------

def test_segment_empty_trace():
    result = segment_trace([], trace_id="empty", workflow_name="test")
    assert result.total_tasks == 0
    assert result.autonomous_count == 0
    assert result.unknown_count == 0
    assert result.autonomy.tag == EpistemicTag.UNKNOWN
    assert result.autonomy.value is None


# ---------------------------------------------------------------------------
# Test: single autonomous span
# ---------------------------------------------------------------------------

def test_segment_single_autonomous_span():
    span = _make_span("s1", "llm_call", start_offset_s=0, duration_s=2.0)
    result = segment_trace([span], trace_id="trace-auto")
    assert result.total_tasks == 1
    assert result.autonomous_count == 1
    assert result.human_explicit_count == 0
    assert result.human_inferred_count == 0
    assert result.unknown_count == 0
    task = result.tasks[0]
    assert task.outcome == TaskOutcome.AUTONOMOUS
    assert task.epistemic_tag == EpistemicTag.OBSERVED
    assert "s1" in task.span_ids


# ---------------------------------------------------------------------------
# Test: explicit human intervention
# ---------------------------------------------------------------------------

def test_segment_explicit_human_span():
    span = _make_span(
        "s1", "human_review",
        start_offset_s=0, duration_s=5.0,
        is_human=True, detection="OBSERVED_TELEMETRY",
        human_action="review_output",
    )
    result = segment_trace([span], trace_id="trace-human")
    assert result.human_explicit_count == 1
    assert result.autonomous_count == 0
    task = result.tasks[0]
    assert task.outcome == TaskOutcome.HUMAN_EXPLICIT
    assert task.epistemic_tag == EpistemicTag.OBSERVED


# ---------------------------------------------------------------------------
# Test: inferred heuristic human intervention
# ---------------------------------------------------------------------------

def test_segment_inferred_human_span():
    span = _make_span(
        "s1", "slow_response",
        start_offset_s=0, duration_s=60.0,
        is_human=True, detection="INFERRED_HEURISTIC_LATENCY",
    )
    result = segment_trace([span], trace_id="trace-inferred")
    assert result.human_inferred_count == 1
    assert result.human_explicit_count == 0
    task = result.tasks[0]
    assert task.outcome == TaskOutcome.HUMAN_INFERRED
    assert task.epistemic_tag == EpistemicTag.INFERRED


# ---------------------------------------------------------------------------
# Test: large gap produces UNKNOWN task
# ---------------------------------------------------------------------------

def test_segment_gap_produces_unknown_task():
    span_a = _make_span("s1", "step_a", start_offset_s=0, duration_s=2.0)
    # 60-second gap then second span
    span_b = _make_span("s2", "step_b", start_offset_s=62.0, duration_s=2.0)
    result = segment_trace(
        [span_a, span_b],
        trace_id="trace-gap",
        gap_heuristic_ms=10_000,  # 10s threshold; 60s gap exceeds it
    )
    # Should have: task(step_a) + UNKNOWN gap + task(step_b)
    assert result.total_tasks == 3
    assert result.unknown_count == 1
    assert result.autonomous_count == 2
    unknown_tasks = [t for t in result.tasks if t.outcome == TaskOutcome.UNKNOWN]
    assert len(unknown_tasks) == 1
    assert unknown_tasks[0].gap_before_ms > 0
    assert unknown_tasks[0].name == "[uninstrumented_gap]"
    assert len(result.notes) >= 1


# ---------------------------------------------------------------------------
# Test: gap below threshold does not create UNKNOWN task
# ---------------------------------------------------------------------------

def test_segment_small_gap_no_unknown():
    span_a = _make_span("s1", "step_a", start_offset_s=0, duration_s=1.0)
    span_b = _make_span("s2", "step_b", start_offset_s=1.005, duration_s=1.0)  # 5ms gap
    result = segment_trace(
        [span_a, span_b],
        trace_id="trace-small-gap",
        gap_heuristic_ms=30_000,
    )
    # Both spans in same cluster → one task
    assert result.total_tasks == 1
    assert result.autonomous_count == 1
    assert result.unknown_count == 0


# ---------------------------------------------------------------------------
# Test: mixed trace (autonomous + explicit human + gap)
# ---------------------------------------------------------------------------

def test_segment_mixed_trace():
    spans = [
        _make_span("s1", "llm_call", start_offset_s=0, duration_s=2.0),
        _make_span(
            "s2", "human_approval",
            start_offset_s=3.0, duration_s=5.0,
            is_human=True, detection="OBSERVED_TELEMETRY",
        ),
        # 45-second gap after s2
        _make_span("s3", "final_action", start_offset_s=53.0, duration_s=1.0),
    ]
    result = segment_trace(spans, trace_id="trace-mixed", gap_heuristic_ms=10_000)
    assert result.autonomous_count >= 1
    assert result.human_explicit_count >= 1
    assert result.unknown_count >= 1
    # Autonomy bounds: lower < upper due to unknown tasks
    assert result.autonomy.bounds.lower <= result.autonomy.bounds.upper


# ---------------------------------------------------------------------------
# Test: autonomy bounds arithmetic
# ---------------------------------------------------------------------------

def test_autonomy_bounds_arithmetic():
    # 3 autonomous + 1 explicit human + 1 unknown
    spans_autonomous = [
        _make_span(f"s{i}", f"step_{i}", start_offset_s=i * 2.0, duration_s=1.0)
        for i in range(3)
    ]
    span_human = _make_span(
        "h1", "human_step",
        start_offset_s=10.0, duration_s=2.0,
        is_human=True, detection="OBSERVED_TELEMETRY",
    )
    span_after_gap = _make_span("s4", "post_gap", start_offset_s=100.0, duration_s=1.0)
    result = segment_trace(
        spans_autonomous + [span_human, span_after_gap],
        trace_id="trace-bounds",
        gap_heuristic_ms=10_000,
    )
    bounds = result.autonomy.bounds
    # Lower bound = autonomous / total; upper bound = (autonomous + unknown) / total
    total = result.total_tasks
    expected_lower = result.autonomous_count / total * 100.0
    expected_upper = (result.autonomous_count + result.unknown_count) / total * 100.0
    assert abs(bounds.lower - expected_lower) < 0.01
    assert abs(bounds.upper - expected_upper) < 0.01
    assert bounds.lower <= bounds.point_estimate <= bounds.upper


# ---------------------------------------------------------------------------
# Test: unknown-only trace
# ---------------------------------------------------------------------------

def test_autonomy_unknown_only_trace():
    """When there are no spans, autonomy must be UNKNOWN — not zero."""
    result = segment_trace([], trace_id="empty-trace")
    assert result.autonomy.tag == EpistemicTag.UNKNOWN
    assert result.autonomy.value is None


# ---------------------------------------------------------------------------
# Test: aggregate across traces
# ---------------------------------------------------------------------------

def test_aggregate_across_traces():
    spans_a = [_make_span("a1", "task", start_offset_s=0, duration_s=1.0)]
    spans_b = [
        _make_span("b1", "task", start_offset_s=0, duration_s=1.0, trace_id="trace-b"),
        _make_span("b2", "human", start_offset_s=2.0, duration_s=1.0,
                   trace_id="trace-b", is_human=True, detection="OBSERVED_TELEMETRY"),
    ]
    r_a = segment_trace(spans_a, trace_id="trace-a")
    r_b = segment_trace(spans_b, trace_id="trace-b")
    agg = aggregate_autonomy_across_traces([r_a, r_b])

    assert agg.sample_size == r_a.total_tasks + r_b.total_tasks
    assert agg.value is not None
    assert agg.bounds.lower <= agg.bounds.upper


def test_aggregate_empty():
    agg = aggregate_autonomy_across_traces([])
    assert agg.tag == EpistemicTag.UNKNOWN
    assert agg.value is None


# ---------------------------------------------------------------------------
# Test: determinism (same input → same output)
# ---------------------------------------------------------------------------

def test_segmentation_is_deterministic():
    spans = [
        _make_span("d1", "step_a", start_offset_s=0, duration_s=1.0),
        _make_span("d2", "step_b", start_offset_s=60.0, duration_s=1.0),
    ]
    r1 = segment_trace(spans, trace_id="det-trace", gap_heuristic_ms=5_000)
    r2 = segment_trace(spans, trace_id="det-trace", gap_heuristic_ms=5_000)
    assert r1.to_dict() == r2.to_dict()


# ---------------------------------------------------------------------------
# Test: to_dict() serialization
# ---------------------------------------------------------------------------

def test_segmentation_to_dict():
    span = _make_span("s1", "compute", start_offset_s=0, duration_s=1.5)
    result = segment_trace([span], trace_id="trace-serial")
    d = result.to_dict()
    assert "trace_id" in d
    assert "autonomy" in d
    assert "tasks" in d
    assert len(d["tasks"]) == result.total_tasks
    task_d = d["tasks"][0]
    assert "outcome" in task_d
    assert "epistemic_tag" in task_d
    assert "trust_level" in task_d


# ---------------------------------------------------------------------------
# Test: trust level minimum propagation
# ---------------------------------------------------------------------------

def test_trust_level_minimum_propagation():
    """The result trust level should be the minimum across all spans."""
    span_t2 = _make_span("t2s", "high", start_offset_s=0, duration_s=1.0,
                          trust_level=TrustLevel.T2)
    span_t0 = _make_span("t0s", "low",  start_offset_s=2.0, duration_s=1.0,
                          trust_level=TrustLevel.T0)
    result = segment_trace([span_t2, span_t0], trace_id="trust-test")
    assert result.min_trust_level == TrustLevel.T0


# ---------------------------------------------------------------------------
# Test: span ordering does not affect outcome (idempotent on order)
# ---------------------------------------------------------------------------

def test_unsorted_spans_same_result():
    spans = [
        _make_span("s2", "second", start_offset_s=2.0, duration_s=1.0),
        _make_span("s1", "first",  start_offset_s=0.0, duration_s=1.0),
        _make_span("s3", "third",  start_offset_s=4.0, duration_s=1.0),
    ]
    result = segment_trace(spans, trace_id="order-test")
    # All within a 30s window → one task
    assert result.total_tasks == 1
    assert "s1" in result.tasks[0].span_ids
    assert "s2" in result.tasks[0].span_ids
    assert "s3" in result.tasks[0].span_ids
