"""
Comprehensive Unit Tests for Epistemic Foundations, Claim Schema, and Ground-Truth Benchmarks.
Validates Gate 1 exit criteria:
- Epistemic tag propagation & integrity
- Trust ladder ranking and requirement enforcement
- Mathematical uncertainty bounds widening under uninstrumented unknowns
- Deterministic claim verification against EpistemicValues
- Seeded-failure ground-truth benchmark accuracy
"""

import pytest
from app.epistemic.tags import (
    EpistemicTag, TrustLevel, VerificationVerdict,
    ConfidenceBounds, EpistemicValue, compute_autonomy_bounds
)
from app.epistemic.claims import (
    ClaimSchema, ClaimDimension, ComparisonOperator,
    ClaimVerificationResult, verify_claim_against_evidence
)
from app.benchmarks.ground_truth import (
    BenchmarkType, GroundTruthResult, generate_ground_truth_benchmark
)

def test_epistemic_tags_enumeration():
    assert EpistemicTag.OBSERVED.value == "[OBSERVED]"
    assert EpistemicTag.CALCULATED.value == "[CALCULATED]"
    assert EpistemicTag.INFERRED.value == "[INFERRED]"
    assert EpistemicTag.UNKNOWN.value == "[UNKNOWN]"

def test_trust_ladder_hierarchy():
    assert TrustLevel.T0.rank < TrustLevel.T1.rank < TrustLevel.T2.rank < TrustLevel.T3.rank
    assert TrustLevel.T3.satisfies_minimum(TrustLevel.T1) is True
    assert TrustLevel.T2.satisfies_minimum(TrustLevel.T2) is True
    assert TrustLevel.T1.satisfies_minimum(TrustLevel.T2) is False
    assert TrustLevel.T0.satisfies_minimum(TrustLevel.T1) is False

def test_autonomy_bounds_no_unknowns():
    # 90 autonomous, 10 human explicit, 0 inferred, 0 unknown
    bounds, unknown_frac = compute_autonomy_bounds(90, 10, 0, 0)
    assert bounds.lower == 90.0
    assert bounds.upper == 90.0
    assert bounds.point_estimate == 90.0
    assert bounds.spread == 0.0
    assert unknown_frac == 0.0

def test_autonomy_bounds_widens_with_unknowns():
    # 70 autonomous, 10 human, 20 uninstrumented/unknown
    bounds, unknown_frac = compute_autonomy_bounds(70, 10, 0, 20)
    # Lower bound treats unknowns as non-autonomous: 70 / 100 = 70.0%
    # Upper bound assumes unknowns were autonomous: (70 + 20) / 100 = 90.0%
    assert bounds.lower == 70.0
    assert bounds.upper == 90.0
    assert bounds.spread == 20.0
    assert unknown_frac == 0.20

def test_autonomy_bounds_zero_tasks_safe():
    bounds, unknown_frac = compute_autonomy_bounds(0, 0, 0, 0)
    assert bounds.lower == 0.0
    assert bounds.upper == 0.0
    assert unknown_frac == 0.0

def test_claim_verification_autonomy_verified():
    claim = ClaimSchema(
        claim_id="CLM-01",
        dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="90% Autonomous",
        target_operator=ComparisonOperator.GREATER_EQUAL,
        target_value=90.0,
        unit="%",
        evidence_trust_minimum=TrustLevel.T1
    )
    evidence = EpistemicValue(
        value=92.5,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=91.0, point_estimate=92.5, upper=94.0),
        sample_size=100,
        unknown_fraction=0.03
    )
    res = verify_claim_against_evidence(claim, evidence)
    assert res.verdict == VerificationVerdict.VERIFIED
    assert "meets or exceeds" in res.reasoning

def test_claim_verification_autonomy_partially_verified():
    claim = ClaimSchema(
        claim_id="CLM-02",
        dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="95% Autonomous",
        target_operator=ComparisonOperator.GREATER_EQUAL,
        target_value=95.0,
        unit="%",
        tolerance_pct=5.0
    )
    # Lower bound is 92.0%, which is within 5% tolerance of 95%
    evidence = EpistemicValue(
        value=92.0,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=92.0, point_estimate=93.0, upper=95.0),
        sample_size=100,
        unknown_fraction=0.02
    )
    res = verify_claim_against_evidence(claim, evidence)
    assert res.verdict == VerificationVerdict.PARTIALLY_VERIFIED

def test_claim_verification_autonomy_contradicted():
    claim = ClaimSchema(
        claim_id="CLM-03",
        dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="95% Autonomous",
        target_operator=ComparisonOperator.GREATER_EQUAL,
        target_value=95.0,
        unit="%",
        tolerance_pct=5.0
    )
    # Observed lower bound is 71.0% -> shortfall of 24.0%
    evidence = EpistemicValue(
        value=71.0,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=71.0, point_estimate=75.0, upper=80.0),
        sample_size=200,
        unknown_fraction=0.05
    )
    res = verify_claim_against_evidence(claim, evidence)
    assert res.verdict == VerificationVerdict.CONTRADICTED

def test_claim_verification_trust_ladder_enforcement():
    claim = ClaimSchema(
        claim_id="CLM-04",
        dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="95% Autonomous",
        target_operator=ComparisonOperator.GREATER_EQUAL,
        target_value=95.0,
        unit="%",
        evidence_trust_minimum=TrustLevel.T1 # Requires at least in-process telemetry
    )
    # Evidence provided is only T0 (self-reported pitch deck claim)
    evidence = EpistemicValue(
        value=98.0,
        tag=EpistemicTag.OBSERVED,
        trust_level=TrustLevel.T0,
        bounds=ConfidenceBounds(lower=98.0, point_estimate=98.0, upper=98.0),
        sample_size=500
    )
    res = verify_claim_against_evidence(claim, evidence)
    assert res.verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE
    assert "Self-reports alone cannot independently verify" in res.reasoning

def test_claim_verification_small_sample_size():
    claim = ClaimSchema(
        claim_id="CLM-05",
        dimension=ClaimDimension.UNIT_COST,
        stated_claim_text="$0.01 per task",
        target_operator=ComparisonOperator.LESS_EQUAL,
        target_value=0.01,
        unit="USD"
    )
    evidence = EpistemicValue(
        value=0.005,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        sample_size=5 # Below minimum threshold of 15
    )
    res = verify_claim_against_evidence(claim, evidence, min_sample_size=15)
    assert res.verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE
    assert "insufficient to verify claim" in res.reasoning

def test_claim_verification_excessive_unknown_intervals():
    claim = ClaimSchema(
        claim_id="CLM-06",
        dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="90% Autonomous",
        target_operator=ComparisonOperator.GREATER_EQUAL,
        target_value=90.0,
        unit="%"
    )
    # 45% of tasks are uninstrumented/unknown
    evidence = EpistemicValue(
        value=85.0,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=50.0, point_estimate=65.0, upper=95.0),
        sample_size=100,
        unknown_fraction=0.45
    )
    res = verify_claim_against_evidence(claim, evidence)
    assert res.verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE
    assert "Uninstrumented intervals represent 45.0%" in res.reasoning

# Ground-Truth Benchmark Tests
def test_benchmark_alpha_silent_escalation():
    gt = generate_ground_truth_benchmark(BenchmarkType.ALPHA_SILENT_ESCALATION, sample_size=500, seed=42)
    assert gt.total_tasks == 500
    assert gt.autonomous_tasks == 360 # 72%
    assert gt.explicit_hitl_tasks == 140 # 28%
    assert gt.expected_autonomy_lower == 72.0
    assert gt.expected_autonomy_upper == 72.0
    
    # Evaluate against founder claim of 95% autonomy
    claim = gt.claims[0]
    evidence = EpistemicValue(
        value=gt.expected_autonomy_lower,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=gt.expected_autonomy_lower, point_estimate=gt.expected_autonomy_lower, upper=gt.expected_autonomy_upper),
        sample_size=gt.total_tasks,
        unknown_fraction=gt.expected_unknown_fraction
    )
    result = verify_claim_against_evidence(claim, evidence)
    assert result.verdict == VerificationVerdict.CONTRADICTED

def test_benchmark_beta_retry_cascade():
    gt = generate_ground_truth_benchmark(BenchmarkType.BETA_RETRY_CASCADE, sample_size=300, seed=42)
    assert gt.total_tasks == 300
    assert gt.expected_retry_multiplier > 2.0 # Confirms retry storm cost escalation
    assert gt.expected_cost_per_task > 0.0010
    
    # Evaluate claim of $0.0010/task
    claim = gt.claims[0]
    evidence = EpistemicValue(
        value=gt.expected_cost_per_task,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=gt.expected_cost_per_task, point_estimate=gt.expected_cost_per_task, upper=gt.expected_cost_per_task),
        sample_size=gt.total_tasks
    )
    result = verify_claim_against_evidence(claim, evidence)
    assert result.verdict == VerificationVerdict.CONTRADICTED

def test_benchmark_gamma_dark_intervals_widens_bounds():
    gt = generate_ground_truth_benchmark(BenchmarkType.GAMMA_DARK_INTERVALS, sample_size=400, seed=42)
    assert gt.dark_interval_tasks == 60 # 15%
    assert gt.expected_unknown_fraction == 0.15
    # Bounds should span exactly 15% points between lower and upper
    assert round(gt.expected_autonomy_upper - gt.expected_autonomy_lower, 2) == 15.0

def test_benchmark_delta_provider_concentration():
    gt = generate_ground_truth_benchmark(BenchmarkType.DELTA_PROVIDER_CONCENTRATION, sample_size=200, seed=42)
    # HHI = (0.90)^2 + (0.10)^2 = 0.81 + 0.01 = 0.82
    assert gt.expected_hhi == 0.82
    claim = gt.claims[0] # claims multi-cloud resilience HHI <= 0.50
    evidence = EpistemicValue(
        value=gt.expected_hhi,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=gt.expected_hhi, point_estimate=gt.expected_hhi, upper=gt.expected_hhi),
        sample_size=gt.total_tasks
    )
    result = verify_claim_against_evidence(claim, evidence)
    assert result.verdict == VerificationVerdict.CONTRADICTED
