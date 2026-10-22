"""
Phase 1-3 Adversarial & Property-Based Regression Tests.

These tests target LOGICAL INVARIANTS rather than repeating implementation assumptions.
Expected results are computed INDEPENDENTLY to avoid circular verification.

Findings addressed:
  - F-001: Epoch sentinel (1970-01-01) must not generate spurious UNKNOWN gaps
  - F-002: HHI scale must be 0-10,000 throughout the metrics engine
  - F-003: TCR must not silently mark tasks complete with zero span evidence
  - F-004: Autonomy bounds invariant: lower <= point_estimate <= upper, spread >= 0
  - F-005: Unknown tasks always widen or preserve bounds (never collapse them)
  - F-006: Missing evidence never improves a verdict
  - F-007: Inferred interventions must not produce OBSERVED epistemic tag
  - F-008: verifier.py sample threshold consistency (N >= 15)
  - F-009: HHI always in [0, 10000] for valid nonneg inputs
  - F-010: Duplicate ingestion must not distort autonomy bounds beyond the accounted tasks
"""

import pytest
from datetime import datetime, timedelta
from typing import List

from app.analysis.task_segmentation import segment_trace, TaskOutcome
from app.analysis.metrics_engine import compute_diligence_metrics, _compute_hhi
from app.epistemic.tags import (
    EpistemicTag, TrustLevel, ConfidenceBounds, EpistemicValue,
    compute_autonomy_bounds, VerificationVerdict
)
from app.epistemic.claims import (
    ClaimSchema, ClaimDimension, ComparisonOperator, verify_claim_against_evidence
)
from app.ingestion.schema import NormalizedSpan
from app.evidence.verifier import (
    verify_autonomy_claim, verify_economics_claim, verify_dependency_claim
)
from app.db.models import VerificationStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _span(
    span_id, name, start_s, dur_s, *,
    trace_id="trace-adv-001",
    is_human=False,
    detection="OBSERVED_TELEMETRY",
    status_code="OK",
    input_tokens=None,
    output_tokens=None,
    provider="openai",
    cost_usd=0.001,
    cost_status="MEASURED",
    trust_level=TrustLevel.T1,
):
    base = datetime(2026, 6, 1, 0, 0, 0)
    s = base + timedelta(seconds=start_s)
    e = s + timedelta(seconds=dur_s)
    return NormalizedSpan(
        span_id=span_id, trace_id=trace_id, name=name, span_kind="INTERNAL",
        start_time=s, end_time=e, duration_ms=dur_s * 1000.0, status_code=status_code,
        is_human_intervention=is_human,
        intervention_detection_method=detection if is_human else None,
        input_tokens=input_tokens, output_tokens=output_tokens,
        has_token_data=(input_tokens is not None or output_tokens is not None),
        provider_name=provider, cost_usd=cost_usd, cost_status=cost_status,
        trust_level=trust_level,
    )


def _epoch_span(span_id, name, trace_id="trace-sentinel"):
    epoch = datetime(1970, 1, 1, 0, 0, 0)
    return NormalizedSpan(
        span_id=span_id, trace_id=trace_id, name=name, span_kind="INTERNAL",
        start_time=epoch, end_time=epoch, duration_ms=0.0, status_code="OK",
        provider_name=None, cost_usd=0.0, cost_status="UNKNOWN",
        trust_level=TrustLevel.T1,
    )


# ---------------------------------------------------------------------------
# F-001: Epoch sentinel must not generate spurious 50-year UNKNOWN gaps
# ---------------------------------------------------------------------------

def test_epoch_only_trace_returns_zero_tasks():
    spans = [_epoch_span("e1", "missing_ts_a"), _epoch_span("e2", "missing_ts_b")]
    result = segment_trace(spans, trace_id="epoch-only")
    assert result.total_tasks == 0
    assert result.autonomy.tag == EpistemicTag.UNKNOWN


def test_epoch_plus_real_span_no_false_gap():
    real_span = _span("r1", "real_call", 0.0, 1.0, trace_id="mixed-sentinel")
    epoch_s = _epoch_span("e1", "missing_ts", trace_id="mixed-sentinel")
    result = segment_trace([epoch_s, real_span], trace_id="mixed-sentinel")
    unknown_tasks = [t for t in result.tasks if t.outcome == TaskOutcome.UNKNOWN]
    assert len(unknown_tasks) == 0, (
        f"Found {len(unknown_tasks)} UNKNOWN gap tasks from epoch sentinel. Tasks: {[t.name for t in result.tasks]}"
    )


def test_epoch_span_noted_in_result():
    real_span = _span("r1", "real", 0.0, 1.0, trace_id="disclosure-test")
    epoch_s = _epoch_span("e1", "sentinel", trace_id="disclosure-test")
    result = segment_trace([epoch_s, real_span], trace_id="disclosure-test")
    note_text = " ".join(result.notes).lower()
    assert any(kw in note_text for kw in ["epoch", "missing", "sentinel"]), (
        f"Epoch sentinel not disclosed. Notes: {result.notes}"
    )


# ---------------------------------------------------------------------------
# F-002: HHI scale invariants (0-10,000)
# ---------------------------------------------------------------------------

def test_hhi_single_provider_is_10000():
    spans = [_span(f"s{i}", f"call_{i}", i * 2.0, 1.0, provider="openai") for i in range(5)]
    seg = segment_trace(spans, trace_id="hhi-single")
    metrics = compute_diligence_metrics([seg], spans)
    assert metrics.model_concentration.value == 10000.0


def test_hhi_two_equal_providers_hand_computed():
    """50/50 split: HHI = 2 * 0.5^2 * 10000 = 5000 (hand-computed)."""
    spans = (
        [_span(f"a{i}", f"a_{i}", i * 2.0, 1.0, provider="openai") for i in range(5)] +
        [_span(f"b{i}", f"b_{i}", (i + 10) * 2.0, 1.0, provider="anthropic") for i in range(5)]
    )
    seg = segment_trace(spans, trace_id="hhi-equal")
    metrics = compute_diligence_metrics([seg], spans)
    assert abs(metrics.model_concentration.value - 5000.0) < 1.0


def test_hhi_90_10_split_hand_computed():
    """90/10 split: HHI = (0.81 + 0.01) * 10000 = 8200 (hand-computed)."""
    spans = (
        [_span(f"a{i}", f"a_{i}", i * 2.0, 1.0, provider="openai") for i in range(9)] +
        [_span("b0", "b_0", 20.0, 1.0, provider="anthropic")]
    )
    seg = segment_trace(spans, trace_id="hhi-90-10")
    metrics = compute_diligence_metrics([seg], spans)
    assert abs(metrics.model_concentration.value - 8200.0) < 10.0, (
        f"Expected ~8200 but got {metrics.model_concentration.value}"
    )


@pytest.mark.parametrize("provider_cfg,label", [
    ([_span("s1", "x", 0, 1, provider="openai")], "single"),
    ([_span("s1", "x", 0, 1, provider=None)], "no-provider"),
    ([], "empty"),
])
def test_hhi_always_in_valid_range(provider_cfg, label):
    seg = segment_trace(provider_cfg, trace_id=f"hhi-range-{label}") if provider_cfg else None
    segs = [seg] if seg else []
    metrics = compute_diligence_metrics(segs, provider_cfg)
    v = metrics.model_concentration.value
    assert 0.0 <= v <= 10000.0, f"HHI={v} out of range for case '{label}'"


# ---------------------------------------------------------------------------
# F-003: TCR must not silently assert completion with zero evidence
# ---------------------------------------------------------------------------

def test_tcr_error_only_span_not_completed():
    """Task with only ERROR spans must NOT count as completed (lower bound = 0%)."""
    spans = [_span("s1", "step", 0.0, 1.0, status_code="ERROR")]
    seg = segment_trace(spans, trace_id="tcr-error")
    metrics = compute_diligence_metrics([seg], spans)
    assert metrics.task_completion_rate.bounds.lower == 0.0, (
        f"ERROR-only task wrongly counted completed. TCR lower={metrics.task_completion_rate.bounds.lower}"
    )


def test_tcr_unknown_gap_never_counted_as_completed():
    """UNKNOWN gap tasks must appear in upper bound widening but NOT in lower bound."""
    spans = [
        _span("s1", "before", 0.0, 1.0, status_code="OK"),
        _span("s2", "after", 100.0, 1.0, status_code="OK"),
    ]
    seg = segment_trace(spans, trace_id="tcr-gap", gap_heuristic_ms=5_000)
    unknown_tasks = [t for t in seg.tasks if t.outcome == TaskOutcome.UNKNOWN]
    assert len(unknown_tasks) >= 1, "Expected at least one UNKNOWN gap"
    metrics = compute_diligence_metrics([seg], spans)
    total = seg.total_tasks  # e.g., 3: before, gap, after
    completed_real = 2  # 2 OK spans
    expected_lower = completed_real / total * 100.0
    expected_upper = (completed_real + len(unknown_tasks)) / total * 100.0
    assert abs(metrics.task_completion_rate.bounds.lower - expected_lower) < 2.0
    assert abs(metrics.task_completion_rate.bounds.upper - expected_upper) < 2.0


# ---------------------------------------------------------------------------
# F-004: Autonomy bounds mathematical invariants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("auto,hexp,hinf,unk", [
    (0, 0, 0, 0), (10, 0, 0, 0), (0, 10, 0, 0), (0, 0, 0, 10),
    (7, 2, 1, 0), (7, 1, 1, 1), (100, 0, 0, 0), (0, 0, 0, 100), (50, 0, 0, 50),
])
def test_autonomy_bounds_invariants(auto, hexp, hinf, unk):
    bounds, frac = compute_autonomy_bounds(auto, hexp, hinf, unk)
    assert bounds.lower <= bounds.point_estimate <= bounds.upper
    assert bounds.spread >= 0.0
    assert 0.0 <= bounds.lower <= 100.0
    assert 0.0 <= bounds.upper <= 100.0


def test_unknown_tasks_widen_bounds_spread():
    """Adding unknown tasks must widen the bounds SPREAD (upper - lower).
    Formula: lower=auto/total, upper=(auto+unk)/total.
    Adding 1 unknown increases total → lower DECREASES (more conservative) and
    upper INCREASES (more optimistic). Spread = upper - lower GROWS.
    """
    bounds_no_unk, _ = compute_autonomy_bounds(7, 1, 1, 0)  # total=9, lower=upper=77.78%
    bounds_with_unk, _ = compute_autonomy_bounds(7, 1, 1, 1)  # total=10, lower=70%, upper=80%
    assert bounds_with_unk.spread > bounds_no_unk.spread, (
        f"Unknown tasks did not widen spread. "
        f"No-unk spread={bounds_no_unk.spread:.2f}, with-unk spread={bounds_with_unk.spread:.2f}"
    )
    assert bounds_with_unk.upper > bounds_no_unk.upper, "Unknown tasks must increase upper bound"
    assert bounds_with_unk.lower < bounds_no_unk.lower, (
        "Unknown tasks must decrease lower bound (more conservative denominator)"
    )


def test_hand_computed_gamma_dark_intervals():
    """400 tasks: 300 auto, 40 explicit, 0 inferred, 60 dark.
    lower = 300/400 = 75.0%
    upper = (300+60)/400 = 90.0%
    spread = 15.0%
    """
    bounds, frac = compute_autonomy_bounds(300, 40, 0, 60)
    assert abs(bounds.lower - 75.0) < 0.01
    assert abs(bounds.upper - 90.0) < 0.01
    assert abs(bounds.spread - 15.0) < 0.01
    assert abs(frac - 0.15) < 0.001


def test_zero_unknowns_gives_zero_spread():
    bounds, frac = compute_autonomy_bounds(80, 20, 0, 0)
    assert bounds.lower == bounds.upper == bounds.point_estimate
    assert bounds.spread == 0.0
    assert frac == 0.0


# ---------------------------------------------------------------------------
# F-005: Missing evidence never improves a verdict
# ---------------------------------------------------------------------------

def test_t0_evidence_insufficient_regardless_of_value():
    claim = ClaimSchema(
        claim_id="TEST-T0", dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="99% Autonomous",
        target_operator=ComparisonOperator.GREATER_EQUAL, target_value=99.0, unit="%",
        evidence_trust_minimum=TrustLevel.T1,
    )
    evidence = EpistemicValue(
        value=100.0, tag=EpistemicTag.OBSERVED, trust_level=TrustLevel.T0,
        bounds=ConfidenceBounds(lower=100.0, point_estimate=100.0, upper=100.0),
        sample_size=1000, unknown_fraction=0.0,
    )
    result = verify_claim_against_evidence(claim, evidence)
    assert result.verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("n", [0, 1, 5, 14])
def test_insufficient_sample_always_blocks_verification(n):
    claim = ClaimSchema(
        claim_id="TEST-SAMPLE", dimension=ClaimDimension.UNIT_COST,
        stated_claim_text=".001/task",
        target_operator=ComparisonOperator.LESS_EQUAL, target_value=0.001, unit="USD",
    )
    evidence = EpistemicValue(value=0.0001, tag=EpistemicTag.CALCULATED, trust_level=TrustLevel.T1, sample_size=n)
    result = verify_claim_against_evidence(claim, evidence, min_sample_size=15)
    assert result.verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE


def test_high_unknown_fraction_blocks_verification():
    claim = ClaimSchema(
        claim_id="TEST-DARK", dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="90% Autonomous",
        target_operator=ComparisonOperator.GREATER_EQUAL, target_value=90.0, unit="%",
    )
    evidence = EpistemicValue(
        value=95.0, tag=EpistemicTag.INFERRED, trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=60.0, point_estimate=95.0, upper=100.0),
        sample_size=100, unknown_fraction=0.40,
    )
    result = verify_claim_against_evidence(claim, evidence)
    assert result.verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE


# ---------------------------------------------------------------------------
# F-007: Inferred interventions must produce INFERRED epistemic tag
# ---------------------------------------------------------------------------

def test_inferred_span_produces_inferred_hir_tag():
    spans = [
        _span("s1", "auto", 0.0, 1.0),
        _span("h1", "inferred_human", 2.0, 2.0, is_human=True, detection="INFERRED_HEURISTIC_LATENCY"),
    ]
    seg = segment_trace(spans, trace_id="tag-inferred")
    metrics = compute_diligence_metrics([seg], spans)
    assert metrics.human_intervention_rate.tag == EpistemicTag.INFERRED


def test_explicit_only_produces_observed_hir_tag():
    spans = [
        _span("s1", "auto", 0.0, 1.0),
        _span("h1", "explicit", 2.0, 2.0, is_human=True, detection="OBSERVED_TELEMETRY"),
    ]
    seg = segment_trace(spans, trace_id="tag-explicit")
    metrics = compute_diligence_metrics([seg], spans)
    assert metrics.human_intervention_rate.tag == EpistemicTag.OBSERVED


def test_inferred_task_carries_inferred_epistemic_tag():
    spans = [_span("h1", "inferred_human", 0.0, 1.0, is_human=True, detection="INFERRED_HEURISTIC_LATENCY")]
    seg = segment_trace(spans, trace_id="tag-task-inferred")
    inferred = [t for t in seg.tasks if t.outcome == TaskOutcome.HUMAN_INFERRED]
    assert len(inferred) >= 1
    for t in inferred:
        assert t.epistemic_tag == EpistemicTag.INFERRED, f"Expected INFERRED, got {t.epistemic_tag}"


# ---------------------------------------------------------------------------
# F-008: verifier.py sample threshold consistency (N >= 15)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [0, 1, 10, 14])
def test_autonomy_verifier_threshold_n_lt_15(n):
    status, msg, _ = verify_autonomy_claim("90% autonomy", 90.0, 85.0, sample_size=n)
    assert status == VerificationStatus.INSUFFICIENT_EVIDENCE
    assert "minimum: 15" in msg or "insufficient" in msg.lower()


def test_autonomy_verifier_at_exactly_15():
    status, _, _ = verify_autonomy_claim("90%", 90.0, 92.0, sample_size=15)
    assert status != VerificationStatus.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("n", [0, 1, 10, 14])
def test_economics_verifier_threshold_n_lt_15(n):
    status, msg, _ = verify_economics_claim(".001/task", 0.001, 0.0009, sample_size=n)
    assert status == VerificationStatus.INSUFFICIENT_EVIDENCE
    assert "minimum: 15" in msg or "insufficient" in msg.lower()


# ---------------------------------------------------------------------------
# F-009: HHI verifier uses 0-10,000 scale
# ---------------------------------------------------------------------------

def test_hhi_verifier_single_provider_contradicted():
    status, msg, _ = verify_dependency_claim("multi-cloud", 10000.0, 100.0)
    assert status == VerificationStatus.CONTRADICTED
    assert "/10000" in msg


def test_hhi_verifier_balanced_verified():
    status, _, _ = verify_dependency_claim("multi-cloud", 2500.0, 30.0)
    assert status == VerificationStatus.VERIFIED


def test_hhi_verifier_8200_contradicted():
    status, msg, _ = verify_dependency_claim("multi-cloud", 8200.0, 90.0)
    assert status == VerificationStatus.CONTRADICTED


def test_hhi_verifier_5000_partially_verified():
    status, _, _ = verify_dependency_claim("multi-cloud", 5000.0, 50.0)
    assert status == VerificationStatus.PARTIALLY_VERIFIED


# ---------------------------------------------------------------------------
# F-010: Determinism
# ---------------------------------------------------------------------------

def test_segment_trace_deterministic():
    spans = [
        _span("s1", "a", 0.0, 1.0),
        _span("h1", "explicit", 2.0, 1.0, is_human=True, detection="OBSERVED_TELEMETRY"),
        _span("s3", "c", 100.0, 1.0),
    ]
    r1 = segment_trace(spans, trace_id="det-seg", gap_heuristic_ms=5000)
    r2 = segment_trace(spans, trace_id="det-seg", gap_heuristic_ms=5000)
    assert r1.to_dict() == r2.to_dict()


def test_compute_metrics_deterministic():
    spans = [
        _span("s1", "a", 0.0, 1.0, input_tokens=100, output_tokens=50),
        _span("s2", "b", 2.0, 1.0, provider="anthropic"),
    ]
    seg = segment_trace(spans, trace_id="det-metrics")
    m1 = compute_diligence_metrics([seg], spans).to_dict()
    m2 = compute_diligence_metrics([seg], spans).to_dict()
    assert m1 == m2


# ---------------------------------------------------------------------------
# Property: eligible task counts must reconcile
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario", ["all_auto", "mixed", "with_gap", "all_human"])
def test_task_counts_reconcile(scenario):
    if scenario == "all_auto":
        spans = [_span(f"s{i}", f"step_{i}", i * 2.0, 1.0) for i in range(5)]
        gap_ms = 30_000
    elif scenario == "mixed":
        spans = [
            _span("s1", "auto", 0.0, 1.0),
            _span("h1", "explicit", 2.0, 1.0, is_human=True, detection="OBSERVED_TELEMETRY"),
            _span("h2", "inferred", 4.0, 1.0, is_human=True, detection="INFERRED_HEURISTIC_LATENCY"),
        ]
        gap_ms = 30_000
    elif scenario == "with_gap":
        spans = [_span("s1", "a", 0.0, 1.0), _span("s2", "b", 100.0, 1.0)]
        gap_ms = 5_000
    else:
        spans = [_span("h1", "approval", 0.0, 2.0, is_human=True, detection="OBSERVED_TELEMETRY")]
        gap_ms = 30_000

    result = segment_trace(spans, trace_id=f"reconcile-{scenario}", gap_heuristic_ms=gap_ms)
    assert result.total_tasks == (
        result.autonomous_count + result.human_explicit_count +
        result.human_inferred_count + result.unknown_count
    ), f"Task count mismatch in scenario '{scenario}'"
    assert len(result.tasks) == result.total_tasks
