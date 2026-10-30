"""
Phase 5 Milestone C Tests: Ground-Truth Controlled Pilot.

Validates the 7 deterministic pilot scenarios, empirical ground-truth verification,
and enforces that False-Positive Verification Rate (FPVR) is strictly 0.0%.
"""

import pytest
from app.adapters.pilot import (
    PilotScenarioType,
    run_ground_truth_pilot,
    execute_scenario,
    _generate_autonomous_scenario,
    _generate_human_intervention_scenario,
    _generate_retry_scenario,
    _generate_complete_failure_scenario,
    _generate_suppressed_telemetry_scenario,
    _generate_duplicate_events_scenario,
    _generate_provider_fallback_scenario,
)
from app.epistemic.tags import VerificationVerdict


# ==============================================================================
# 1. Individual Scenario Execution Tests
# ==============================================================================

def test_scenario_1_autonomous_tool_completion():
    """Scenario 1: Agent completes with zero human interventions (100% autonomy)."""
    sc = _generate_autonomous_scenario()
    res = execute_scenario(sc)

    assert res.total_traces == 20
    assert res.total_spans == 60
    assert res.metrics.autonomy_rate.bounds.point_estimate == 100.0
    assert res.metrics.error_rate.bounds.point_estimate == 0.0

    # True positives: claimed autonomy and reliability verified
    assert res.true_positives == 2
    # True negatives: <= 50% claimed autonomy rejected
    assert res.true_negatives == 1
    assert res.false_positives == 0
    assert res.false_negatives == 0


def test_scenario_2_human_intervention():
    """Scenario 2: Explicit human approval stops autonomy (0% autonomy, 100% HIR)."""
    sc = _generate_human_intervention_scenario()
    res = execute_scenario(sc)

    assert res.total_traces == 20
    assert res.metrics.autonomy_rate.bounds.point_estimate == 0.0
    assert res.metrics.human_intervention_rate.bounds.point_estimate == 100.0

    # 90% autonomy claim is CONTRADICTED (TN)
    claim_verdicts = {c["claim_id"]: c["pipeline_verdict"] for c in res.claim_verdicts}
    assert claim_verdicts["CLM-HITL-01"] == VerificationVerdict.CONTRADICTED.value
    # <= 10% autonomy claim is VERIFIED (TP)
    assert claim_verdicts["CLM-HITL-02"] == VerificationVerdict.VERIFIED.value

    assert res.false_positives == 0
    assert res.false_negatives == 0


def test_scenario_3_tool_failure_and_retry():
    """Scenario 3: Transient tool failure recovers on retry (25% error rate)."""
    sc = _generate_retry_scenario()
    res = execute_scenario(sc)

    assert res.total_traces == 20
    assert res.metrics.error_rate.bounds.point_estimate == 25.0

    claim_verdicts = {c["claim_id"]: c["pipeline_verdict"] for c in res.claim_verdicts}
    assert claim_verdicts["CLM-RET-01"] == VerificationVerdict.CONTRADICTED.value
    assert claim_verdicts["CLM-RET-02"] == VerificationVerdict.VERIFIED.value

    assert res.false_positives == 0
    assert res.false_negatives == 0


def test_scenario_4_complete_failure():
    """Scenario 4: Agent aborts on unrecoverable DB error (high error rate)."""
    sc = _generate_complete_failure_scenario()
    res = execute_scenario(sc)

    assert res.total_traces == 20
    assert res.metrics.error_rate.bounds.point_estimate > 50.0

    claim_verdicts = {c["claim_id"]: c["pipeline_verdict"] for c in res.claim_verdicts}
    assert claim_verdicts["CLM-CFL-01"] == VerificationVerdict.CONTRADICTED.value
    assert claim_verdicts["CLM-CFL-02"] == VerificationVerdict.VERIFIED.value

    assert res.false_positives == 0
    assert res.false_negatives == 0


def test_scenario_5_suppressed_telemetry_dark_zone():
    """Scenario 5: >35% dark zone triggers INSUFFICIENT_EVIDENCE, preventing false positive."""
    sc = _generate_suppressed_telemetry_scenario()
    res = execute_scenario(sc)

    assert res.total_traces == 20
    # Must trigger unknown fraction > 0.35
    assert res.metrics.autonomy_rate.unknown_fraction > 0.35

    claim_verdicts = {c["claim_id"]: c["pipeline_verdict"] for c in res.claim_verdicts}
    # Epistemic invariant: dark zone forces INSUFFICIENT_EVIDENCE, NEVER VERIFIED
    assert claim_verdicts["CLM-DRK-01"] == VerificationVerdict.INSUFFICIENT_EVIDENCE.value

    # Confirmed True Negative (rejection of unfounded claim)
    assert res.true_negatives == 1
    assert res.false_positives == 0


def test_scenario_6_duplicate_events():
    """Scenario 6: Transport duplicates are filtered without inflating cost or span count."""
    sc = _generate_duplicate_events_scenario()
    res = execute_scenario(sc)

    # 20 traces * 2 unique spans = 40 spans total (80 raw spans deduplicated)
    assert res.total_traces == 20
    assert res.total_spans == 40

    claim_verdicts = {c["claim_id"]: c["pipeline_verdict"] for c in res.claim_verdicts}
    assert claim_verdicts["CLM-DUP-01"] == VerificationVerdict.VERIFIED.value
    assert res.false_positives == 0


def test_scenario_7_provider_fallback():
    """Scenario 7: Primary rate limit triggers Anthropic fallback, lowering HHI concentration."""
    sc = _generate_provider_fallback_scenario()
    res = execute_scenario(sc)

    assert res.total_traces == 20
    assert res.metrics.model_concentration.bounds.point_estimate <= 6000.0

    claim_verdicts = {c["claim_id"]: c["pipeline_verdict"] for c in res.claim_verdicts}
    assert claim_verdicts["CLM-FBK-01"] == VerificationVerdict.VERIFIED.value
    assert claim_verdicts["CLM-FBK-02"] == VerificationVerdict.CONTRADICTED.value
    assert res.false_positives == 0


# ==============================================================================
# 2. Consolidated Pilot Audit & Epistemic Verification Rates
# ==============================================================================

def test_consolidated_ground_truth_pilot_execution():
    """Consolidated Ground-Truth Pilot across all 7 scenarios achieves 0.0% FPVR."""
    report = run_ground_truth_pilot()

    assert report.total_scenarios == 7
    assert report.total_traces_analyzed == 140
    assert report.total_claims_evaluated >= 12

    # Invariant: Zero False Positives (FPVR == 0.0%)
    assert report.false_positives == 0
    assert report.false_positive_verification_rate == 0.0

    # Invariant: False Negative Verification Rate <= 5%
    assert report.false_negative_verification_rate <= 0.05

    # Verification accuracy should be 100%
    assert report.verification_accuracy == 1.0
    assert report.passed_audit is True

    # Report serializes to valid dict
    d = report.to_dict()
    assert d["passed_audit"] is True
    assert d["confusion_matrix"]["false_positives"] == 0
    assert d["false_positive_verification_rate_pct"] == 0.0


def test_phase6_unified_benchmarks_execution():
    """Phase 6 unified pipeline benchmarks across all 7 scenarios achieve 0% FPVR, 0% FNVR."""
    from app.adapters.benchmarks import run_phase6_benchmarks
    bench = run_phase6_benchmarks()

    assert bench.total_scenarios_evaluated == 7
    assert bench.total_traces_processed == 140
    assert bench.total_claims_evaluated == 13
    assert bench.false_positives == 0
    assert bench.false_negatives == 0
    assert bench.false_positive_verification_rate == 0.0
    assert bench.false_negative_verification_rate == 0.0
    assert bench.verification_accuracy == 1.0
    assert bench.duplicate_detection_accuracy == 1.0
    assert bench.evidence_correlation_accuracy == 1.0
    assert bench.provenance_integrity_failures == 0
    assert bench.mean_ingestion_latency_ms < 50.0
    assert bench.mean_verification_latency_ms < 50.0
    assert bench.passed_audit is True


