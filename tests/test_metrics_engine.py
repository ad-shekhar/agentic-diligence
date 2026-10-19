"""
Phase 3 Tests — Deterministic Metrics Engine.

Verifies all 8 diligence signals across diverse span sets:
  1. Autonomy Rate (AR)
  2. Human Intervention Rate (HIR)
  3. Task Completion Rate (TCR)
  4. Error Rate (ER)
  5. Token Efficiency (TE)
  6. Cost Per Task (CPT)
  7. Model Concentration (MC / HHI)
  8. Telemetry Coverage (TC)

Also verifies:
  - Empty input → UNKNOWN tags throughout
  - Known-formula HHI calculations
  - Epistemic tag correctness per signal
  - Metrics determinism
  - to_dict() serialization
"""

import pytest
from datetime import datetime, timedelta
from app.analysis.task_segmentation import segment_trace
from app.analysis.metrics_engine import compute_diligence_metrics
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
    status_code: str = "OK",
    input_tokens: int = None,
    output_tokens: int = None,
    provider: str = "openai",
    cost_usd: float = 0.01,
    trust_level: TrustLevel = TrustLevel.T1,
    cost_status: str = "MEASURED",
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
        intervention_detection_method=detection if is_human else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        has_token_data=(input_tokens is not None or output_tokens is not None),
        provider_name=provider,
        cost_usd=cost_usd,
        cost_status=cost_status,
        trust_level=trust_level,
    )


def _basic_spans():
    """3 autonomous spans in one trace."""
    return [
        _make_span("s1", "plan",    start_offset_s=0, duration_s=1.0,
                   input_tokens=500, output_tokens=100),
        _make_span("s2", "execute", start_offset_s=2.0, duration_s=1.0,
                   input_tokens=400, output_tokens=200),
        _make_span("s3", "report",  start_offset_s=4.0, duration_s=1.0,
                   input_tokens=300, output_tokens=150, cost_usd=0.005),
    ]


# ---------------------------------------------------------------------------
# Test: empty input
# ---------------------------------------------------------------------------

def test_metrics_empty_input():
    result = compute_diligence_metrics([], [])
    assert result.total_tasks == 0
    assert result.total_spans == 0
    assert result.autonomy_rate.tag == EpistemicTag.UNKNOWN
    assert result.error_rate.tag == EpistemicTag.UNKNOWN


# ---------------------------------------------------------------------------
# Test: autonomy rate signal
# ---------------------------------------------------------------------------

def test_autonomy_rate_all_autonomous():
    spans = _basic_spans()
    seg = segment_trace(spans, trace_id="t1")
    metrics = compute_diligence_metrics([seg], spans)
    ar = metrics.autonomy_rate
    assert ar.value is not None
    assert ar.bounds.lower >= 0.0
    assert ar.bounds.upper <= 100.0
    assert ar.tag in (EpistemicTag.CALCULATED, EpistemicTag.OBSERVED)


def test_autonomy_rate_with_human_explicit():
    spans = _basic_spans() + [
        _make_span("h1", "human_review", start_offset_s=6.0, duration_s=5.0,
                   is_human=True, detection="OBSERVED_TELEMETRY"),
    ]
    seg = segment_trace(spans, trace_id="t2")
    metrics = compute_diligence_metrics([seg], spans)
    # HIR should reflect the explicit human
    assert metrics.human_intervention_rate.value > 0


# ---------------------------------------------------------------------------
# Test: human intervention rate
# ---------------------------------------------------------------------------

def test_hir_explicit_vs_inferred():
    spans = [
        _make_span("s1", "auto", start_offset_s=0, duration_s=1.0),
        _make_span("h1", "observed_human", start_offset_s=2.0, duration_s=2.0,
                   is_human=True, detection="OBSERVED_TELEMETRY"),
        _make_span("h2", "inferred_human", start_offset_s=5.0, duration_s=2.0,
                   is_human=True, detection="INFERRED_HEURISTIC_LATENCY"),
    ]
    seg = segment_trace(spans, trace_id="t3")
    metrics = compute_diligence_metrics([seg], spans)
    hir = metrics.human_intervention_rate
    assert hir.value > 0
    # Inferred spans → tag must be INFERRED
    assert hir.tag == EpistemicTag.INFERRED
    # Lower bound (observed only) ≤ point estimate (observed + inferred)
    assert hir.bounds.lower <= hir.value


# ---------------------------------------------------------------------------
# Test: error rate
# ---------------------------------------------------------------------------

def test_error_rate_zero():
    spans = _basic_spans()
    seg = segment_trace(spans, trace_id="t4")
    metrics = compute_diligence_metrics([seg], spans)
    assert metrics.error_rate.value == 0.0
    assert metrics.error_rate.tag == EpistemicTag.OBSERVED


def test_error_rate_nonzero():
    spans = _basic_spans() + [
        _make_span("e1", "failed_call", start_offset_s=6.0, duration_s=0.5,
                   status_code="ERROR"),
    ]
    seg = segment_trace(spans, trace_id="t5")
    metrics = compute_diligence_metrics([seg], spans)
    assert metrics.error_rate.value > 0
    assert metrics.error_rate.value < 100


# ---------------------------------------------------------------------------
# Test: token efficiency
# ---------------------------------------------------------------------------

def test_token_efficiency_no_token_data():
    spans = [
        _make_span("s1", "no_tokens", start_offset_s=0, duration_s=1.0,
                   input_tokens=None, output_tokens=None),
    ]
    seg = segment_trace(spans, trace_id="t6")
    metrics = compute_diligence_metrics([seg], spans)
    assert metrics.token_efficiency.value is None
    assert metrics.token_efficiency.tag == EpistemicTag.UNKNOWN


def test_token_efficiency_computed():
    # 100 in + 100 out → efficiency = 0.5
    spans = [
        _make_span("s1", "llm", start_offset_s=0, duration_s=1.0,
                   input_tokens=100, output_tokens=100),
    ]
    seg = segment_trace(spans, trace_id="t7")
    metrics = compute_diligence_metrics([seg], spans)
    te = metrics.token_efficiency
    assert te.value is not None
    assert abs(te.value - 0.5) < 0.01
    assert te.tag == EpistemicTag.CALCULATED


def test_token_efficiency_partial_data_inferred():
    spans = [
        _make_span("s1", "llm", start_offset_s=0, duration_s=1.0,
                   input_tokens=200, output_tokens=50),
        _make_span("s2", "no_tok", start_offset_s=2.0, duration_s=1.0),  # no tokens
    ]
    seg = segment_trace(spans, trace_id="t8")
    metrics = compute_diligence_metrics([seg], spans)
    # Partial data → INFERRED
    assert metrics.token_efficiency.tag == EpistemicTag.INFERRED


# ---------------------------------------------------------------------------
# Test: cost per task
# ---------------------------------------------------------------------------

def test_cost_per_task():
    spans = [
        _make_span("s1", "a", start_offset_s=0, duration_s=1.0, cost_usd=0.01),
        _make_span("s2", "b", start_offset_s=2.0, duration_s=1.0, cost_usd=0.03),
    ]
    seg = segment_trace(spans, trace_id="t9")
    metrics = compute_diligence_metrics([seg], spans)
    total_cost = 0.01 + 0.03
    expected_cpt = total_cost / metrics.total_tasks
    assert abs(metrics.cost_per_task.value - expected_cpt) < 0.0001
    assert metrics.total_cost_usd == round(total_cost, 6)


def test_cost_per_task_unpriced_is_inferred():
    spans = [
        _make_span("s1", "a", start_offset_s=0, duration_s=1.0,
                   cost_usd=0.0, cost_status="UNKNOWN"),
    ]
    seg = segment_trace(spans, trace_id="t10")
    metrics = compute_diligence_metrics([seg], spans)
    assert metrics.cost_per_task.tag == EpistemicTag.INFERRED


# ---------------------------------------------------------------------------
# Test: model concentration (HHI)
# ---------------------------------------------------------------------------

def test_hhi_single_provider_is_high():
    spans = [_make_span(f"s{i}", f"call_{i}", i * 2.0, 1.0, provider="openai")
             for i in range(5)]
    seg = segment_trace(spans, trace_id="t11")
    metrics = compute_diligence_metrics([seg], spans)
    # Single provider → HHI = 10000
    assert metrics.model_concentration.value == 10000.0


def test_hhi_two_equal_providers():
    spans = (
        [_make_span(f"a{i}", f"a_{i}", i * 2.0, 1.0, provider="openai")  for i in range(5)] +
        [_make_span(f"b{i}", f"b_{i}", (i+10) * 2.0, 1.0, provider="anthropic") for i in range(5)]
    )
    seg = segment_trace(spans, trace_id="t12")
    metrics = compute_diligence_metrics([seg], spans)
    # 50/50 split → HHI = 2 * (0.5)^2 * 10000 = 5000
    assert abs(metrics.model_concentration.value - 5000.0) < 1.0


def test_hhi_no_provider_spans():
    spans = [_make_span("s1", "no_prov", 0.0, 1.0, provider=None)]
    seg = segment_trace(spans, trace_id="t13")
    metrics = compute_diligence_metrics([seg], spans)
    assert metrics.model_concentration.value == 0.0


# ---------------------------------------------------------------------------
# Test: telemetry coverage
# ---------------------------------------------------------------------------

def test_telemetry_coverage_full():
    spans = [_make_span(f"s{i}", f"s_{i}", i * 2.0, 1.0, trust_level=TrustLevel.T1)
             for i in range(3)]
    seg = segment_trace(spans, trace_id="t14")
    metrics = compute_diligence_metrics([seg], spans)
    assert metrics.telemetry_coverage.value > 0.0


def test_telemetry_coverage_with_gap():
    # Create a gap → UNKNOWN task (T0 by convention)
    spans = [
        _make_span("s1", "before_gap", start_offset_s=0.0, duration_s=1.0),
        _make_span("s2", "after_gap", start_offset_s=100.0, duration_s=1.0),
    ]
    seg = segment_trace(spans, trace_id="t15", gap_heuristic_ms=5_000)
    metrics = compute_diligence_metrics([seg], spans)
    # UNKNOWN tasks reduce coverage
    tc = metrics.telemetry_coverage.value
    assert tc < 100.0


# ---------------------------------------------------------------------------
# Test: metrics determinism
# ---------------------------------------------------------------------------

def test_metrics_determinism():
    spans = _basic_spans()
    seg = segment_trace(spans, trace_id="det")
    m1 = compute_diligence_metrics([seg], spans).to_dict()
    m2 = compute_diligence_metrics([seg], spans).to_dict()
    assert m1 == m2


# ---------------------------------------------------------------------------
# Test: to_dict() serialization
# ---------------------------------------------------------------------------

def test_metrics_to_dict():
    spans = _basic_spans()
    seg = segment_trace(spans, trace_id="serial")
    metrics = compute_diligence_metrics([seg], spans)
    d = metrics.to_dict()
    assert "signals" in d
    signals = d["signals"]
    assert "autonomy_rate" in signals
    assert "human_intervention_rate" in signals
    assert "task_completion_rate" in signals
    assert "error_rate" in signals
    assert "token_efficiency" in signals
    assert "cost_per_task" in signals
    assert "model_concentration" in signals
    assert "telemetry_coverage" in signals
    # Each signal has epistemic fields
    for sig_name, sig_data in signals.items():
        assert "epistemic_tag" in sig_data, f"Missing epistemic_tag in {sig_name}"
        assert "trust_level"   in sig_data, f"Missing trust_level in {sig_name}"
        assert "bounds"        in sig_data, f"Missing bounds in {sig_name}"


# ---------------------------------------------------------------------------
# Test: task completion rate
# ---------------------------------------------------------------------------

def test_task_completion_rate_all_ok():
    spans = _basic_spans()
    seg = segment_trace(spans, trace_id="tcr1")
    metrics = compute_diligence_metrics([seg], spans)
    # All spans have status "OK"
    assert metrics.task_completion_rate.value > 0


def test_task_completion_rate_with_unknown():
    # Gap creates UNKNOWN task which widens the upper bound
    spans = [
        _make_span("s1", "step1", 0.0, 1.0),
        _make_span("s2", "step2", 100.0, 1.0),
    ]
    seg = segment_trace(spans, trace_id="tcr2", gap_heuristic_ms=5_000)
    metrics = compute_diligence_metrics([seg], spans)
    bounds = metrics.task_completion_rate.bounds
    assert bounds.upper >= bounds.lower
