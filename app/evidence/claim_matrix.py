"""
Claim Verification Matrix Engine (Phase 4).

Connects pitch-deck and contractual vendor assertions to empirical runtime telemetry
with deterministic verification, explicit epistemic bounds, and audit traceability.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Any, Dict, List, Tuple
import json

from app.epistemic.tags import (
    EpistemicTag, TrustLevel, VerificationVerdict,
    ConfidenceBounds, EpistemicValue
)
from app.epistemic.claims import ClaimDimension, ComparisonOperator, ClaimSchema


@dataclass
class EvidenceReference:
    """Cryptographic and trace reference connecting a verdict to raw artifacts."""
    artifact_name: str
    artifact_sha256: str
    trace_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "artifact_sha256": self.artifact_sha256,
            "trace_ids": list(self.trace_ids)
        }


@dataclass
class ClaimVerificationMatrixEntry:
    """
    Formal Claim Verification Matrix entry conforming strictly to
    docs/phase-4/data-contracts.md (v1.0 schema).
    """
    claim_id: str
    verbatim_claim_text: str
    claim_source: str
    source_trust_level: TrustLevel
    target_dimension: str
    target_operator: str
    target_threshold: float
    target_units: str
    metric_name: str
    metric_version: str
    metric_denominator: str
    observed_epistemic_value: EpistemicValue
    verification_verdict: VerificationVerdict
    verdict_reason: str
    evidence_references: List[EvidenceReference] = field(default_factory=list)
    limitations_and_assumptions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        obs = self.observed_epistemic_value
        bounds_dict = None
        if obs.bounds:
            bounds_dict = {
                "lower": round(obs.bounds.lower, 4),
                "point": round(obs.bounds.point_estimate, 4),
                "upper": round(obs.bounds.upper, 4)
            }
        elif obs.value is not None:
            bounds_dict = {
                "lower": round(obs.value, 4),
                "point": round(obs.value, 4),
                "upper": round(obs.value, 4)
            }

        return {
            "claim_id": self.claim_id,
            "verbatim_claim_text": self.verbatim_claim_text,
            "claim_source": self.claim_source,
            "source_trust_level": self.source_trust_level.value,
            "target_dimension": self.target_dimension,
            "target_operator": self.target_operator,
            "target_threshold": self.target_threshold,
            "target_units": self.target_units,
            "metric_name": self.metric_name,
            "metric_version": self.metric_version,
            "metric_denominator": self.metric_denominator,
            "observed_epistemic_value": {
                "value": round(obs.value, 4) if obs.value is not None else None,
                "tag": obs.tag.value,
                "trust_level": obs.trust_level.value,
                "bounds": bounds_dict,
                "sample_size": obs.sample_size,
                "unknown_fraction": round(obs.unknown_fraction, 4),
                "notes": obs.notes
            },
            "verification_verdict": self.verification_verdict.value,
            "verdict_reason": self.verdict_reason,
            "evidence_references": [ref.to_dict() for ref in self.evidence_references],
            "limitations_and_assumptions": list(self.limitations_and_assumptions)
        }


@dataclass
class ClaimVerificationMatrix:
    """Collection of evaluated claims for a diligence scope."""
    matrix_id: str
    company_id: str
    generated_at_utc: str
    schema_version: str = "1.0.0"
    entries: List[ClaimVerificationMatrixEntry] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "matrix_id": self.matrix_id,
            "company_id": self.company_id,
            "generated_at_utc": self.generated_at_utc,
            "summary": dict(self.summary),
            "entries": [entry.to_dict() for entry in self.entries]
        }


def evaluate_single_claim(
    claim: ClaimSchema,
    evidence: Optional[EpistemicValue],
    evidence_refs: Optional[List[EvidenceReference]] = None,
    min_sample_size: int = 15,
    metric_denominator_override: Optional[str] = None
) -> ClaimVerificationMatrixEntry:
    """
    Evaluates a single claim against runtime evidence according to strict verification semantics.

    Invariants:
    1. An empty or absent evidence set NEVER produces a positive verdict (returns INSUFFICIENT_EVIDENCE).
    2. Minimum trust level must be satisfied (T0 claim requires >= T1 evidence for runtime proof).
    3. Sample size must meet min_sample_size threshold.
    4. Excessive unknowns (> 35% dark zone) invalidate verification -> INSUFFICIENT_EVIDENCE.
    5. Discrepancies are bounded mathematically via lower/upper intervals.
    """
    refs = list(evidence_refs or [])
    limitations: List[str] = []

    # Map dimensions to standard denominators and metric names
    dim_str = claim.dimension.value if hasattr(claim.dimension, "value") else str(claim.dimension)
    
    denominator_map = {
        "autonomy": "total_tasks",
        "unit_cost": "total_tasks",
        "unit_economics": "total_tasks",
        "eval_cost": "total_cost_usd",
        "evaluation_overhead": "total_cost_usd",
        "provider_spread": "total_model_spend_usd",
        "dependencies": "total_model_spend_usd",
        "provider_concentration": "total_model_spend_usd",
        "least_privilege": "total_tool_calls",
        "reliability": "total_spans",
        "evidence_coverage": "total_workflow_duration_seconds"
    }
    metric_name_map = {
        "autonomy": "autonomy_rate",
        "unit_cost": "cost_per_task_usd",
        "unit_economics": "cost_per_task_usd",
        "eval_cost": "evaluation_overhead_ratio",
        "evaluation_overhead": "evaluation_overhead_ratio",
        "provider_spread": "provider_hhi",
        "dependencies": "provider_hhi",
        "provider_concentration": "provider_hhi",
        "least_privilege": "high_risk_tool_call_rate",
        "reliability": "span_error_rate",
        "evidence_coverage": "telemetry_coverage_ratio"
    }

    metric_name = metric_name_map.get(dim_str, f"{dim_str}_metric")
    metric_denom = metric_denominator_override or denominator_map.get(dim_str, "total_events")

    # Case 1: Absence of Evidence
    if evidence is None or evidence.sample_size == 0:
        limitations.append("Zero runtime evidence was collected for this dimension.")
        empty_evidence = EpistemicValue(
            value=None,
            tag=EpistemicTag.UNKNOWN,
            trust_level=TrustLevel.T0,
            bounds=None,
            sample_size=0,
            unknown_fraction=1.0,
            notes="No telemetry observed for target dimension."
        )
        return ClaimVerificationMatrixEntry(
            claim_id=claim.claim_id,
            verbatim_claim_text=claim.stated_claim_text,
            claim_source=claim.source_document,
            source_trust_level=claim.evidence_trust_minimum,
            target_dimension=dim_str,
            target_operator=claim.target_operator.value,
            target_threshold=claim.target_value,
            target_units=claim.unit,
            metric_name=metric_name,
            metric_version="1.0.0",
            metric_denominator=metric_denom,
            observed_epistemic_value=empty_evidence,
            verification_verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
            verdict_reason="Absence of runtime evidence. Zero traces/tasks observed for this dimension.",
            evidence_references=refs,
            limitations_and_assumptions=limitations
        )

    # Note evidence trust level
    if evidence.trust_level == TrustLevel.T0:
        limitations.append("Evidence relies on self-reported vendor claims (T0).")
    elif evidence.trust_level == TrustLevel.T1:
        limitations.append("Evidence collected via in-process OTel telemetry (T1); host host-trust assumptions apply.")
    elif evidence.trust_level == TrustLevel.T2:
        limitations.append("Evidence validated via independent third-party network proxy observation (T2).")
    elif evidence.trust_level == TrustLevel.T3:
        limitations.append("Evidence cryptographically attested via hardware/billing reconciliation (T3).")

    # Check 1: Trust Level Minimum Check
    if not evidence.trust_level.satisfies_minimum(claim.evidence_trust_minimum):
        limitations.append(
            f"Evidence trust level ({evidence.trust_level.value}) is lower than required minimum ({claim.evidence_trust_minimum.value})."
        )
        return ClaimVerificationMatrixEntry(
            claim_id=claim.claim_id,
            verbatim_claim_text=claim.stated_claim_text,
            claim_source=claim.source_document,
            source_trust_level=claim.evidence_trust_minimum,
            target_dimension=dim_str,
            target_operator=claim.target_operator.value,
            target_threshold=claim.target_value,
            target_units=claim.unit,
            metric_name=metric_name,
            metric_version="1.0.0",
            metric_denominator=metric_denom,
            observed_epistemic_value=evidence,
            verification_verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
            verdict_reason=(
                f"Evidence trust level {evidence.trust_level.value} does not meet required "
                f"minimum trust level {claim.evidence_trust_minimum.value}. Self-reports cannot verify runtime claims."
            ),
            evidence_references=refs,
            limitations_and_assumptions=limitations
        )

    # Check 2: Sample Size Requirement
    if evidence.sample_size < min_sample_size:
        limitations.append(f"Sample size of {evidence.sample_size} is below statistical threshold (N={min_sample_size}).")
        return ClaimVerificationMatrixEntry(
            claim_id=claim.claim_id,
            verbatim_claim_text=claim.stated_claim_text,
            claim_source=claim.source_document,
            source_trust_level=claim.evidence_trust_minimum,
            target_dimension=dim_str,
            target_operator=claim.target_operator.value,
            target_threshold=claim.target_value,
            target_units=claim.unit,
            metric_name=metric_name,
            metric_version="1.0.0",
            metric_denominator=metric_denom,
            observed_epistemic_value=evidence,
            verification_verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
            verdict_reason=(
                f"Sample size of {evidence.sample_size} observations is insufficient "
                f"(minimum requirement: {min_sample_size}) to establish verification status."
            ),
            evidence_references=refs,
            limitations_and_assumptions=limitations
        )

    # Check 3: Excessive Unknowns / Dark Zones (> 35%)
    if evidence.unknown_fraction > 0.35:
        limitations.append(
            f"Uninstrumented dark zones account for {evidence.unknown_fraction * 100:.1f}% of observed execution."
        )
        return ClaimVerificationMatrixEntry(
            claim_id=claim.claim_id,
            verbatim_claim_text=claim.stated_claim_text,
            claim_source=claim.source_document,
            source_trust_level=claim.evidence_trust_minimum,
            target_dimension=dim_str,
            target_operator=claim.target_operator.value,
            target_threshold=claim.target_value,
            target_units=claim.unit,
            metric_name=metric_name,
            metric_version="1.0.0",
            metric_denominator=metric_denom,
            observed_epistemic_value=evidence,
            verification_verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
            verdict_reason=(
                f"Uninstrumented intervals represent {evidence.unknown_fraction * 100:.1f}% of observed volume. "
                f"Missing telemetry produces explicit unknowns, precluding conclusive verification."
            ),
            evidence_references=refs,
            limitations_and_assumptions=limitations
        )

    # Check 4: Deterministic Metric Bounds Evaluation
    bounds = evidence.bounds or ConfidenceBounds(
        lower=evidence.value or 0.0,
        point_estimate=evidence.value or 0.0,
        upper=evidence.value or 0.0
    )
    target = claim.target_value
    op = claim.target_operator
    tol = claim.tolerance_pct

    if evidence.unknown_fraction > 0:
        limitations.append(
            f"Unknown intervals ({evidence.unknown_fraction * 100:.1f}%) widen bounds to [{bounds.lower:.2f}, {bounds.upper:.2f}]."
        )

    if op == ComparisonOperator.GREATER_EQUAL:
        observed_bound = bounds.lower
        diff = observed_bound - target
        if diff >= 0:
            verdict = VerificationVerdict.VERIFIED
            reason = f"Observed conservative lower bound of {observed_bound:.2f} {claim.unit} meets or exceeds target of {target:.2f} {claim.unit}."
        elif abs(diff) <= tol:
            verdict = VerificationVerdict.PARTIALLY_VERIFIED
            reason = f"Observed lower bound of {observed_bound:.2f} {claim.unit} is within allowable tolerance margin ({tol:.1f}%) of stated target {target:.2f} {claim.unit}."
        else:
            verdict = VerificationVerdict.CONTRADICTED
            reason = f"Observed lower bound of {observed_bound:.2f} {claim.unit} contradicts claim; falls below target {target:.2f} {claim.unit} by {abs(diff):.2f}."

    elif op == ComparisonOperator.LESS_EQUAL:
        observed_bound = bounds.upper
        diff = observed_bound - target
        if diff <= 0:
            verdict = VerificationVerdict.VERIFIED
            reason = f"Observed upper bound of {observed_bound:.4f} {claim.unit} complies with target ceiling of {target:.4f} {claim.unit}."
        elif target > 0 and (diff / target) * 100.0 <= tol:
            verdict = VerificationVerdict.PARTIALLY_VERIFIED
            reason = f"Observed upper bound of {observed_bound:.4f} {claim.unit} exceeds target ceiling by {(diff/target)*100.0:.1f}%, within tolerance {tol:.1f}%."
        else:
            ratio = (observed_bound / target) if target > 0 else 1.0
            verdict = VerificationVerdict.CONTRADICTED
            reason = f"Observed upper bound of {observed_bound:.4f} {claim.unit} contradicts claim; exceeds ceiling {target:.4f} {claim.unit} by {ratio:.2f}x."

    else:
        # Equality comparison
        point = bounds.point_estimate
        diff = abs(point - target)
        if diff <= (target * tol / 100.0 if target > 0 else 0.0001):
            verdict = VerificationVerdict.VERIFIED
            reason = f"Observed point estimate {point:.4f} matches target {target:.4f} within tolerance."
        else:
            verdict = VerificationVerdict.CONTRADICTED
            reason = f"Observed point estimate {point:.4f} contradicts target {target:.4f}."

    return ClaimVerificationMatrixEntry(
        claim_id=claim.claim_id,
        verbatim_claim_text=claim.stated_claim_text,
        claim_source=claim.source_document,
        source_trust_level=claim.evidence_trust_minimum,
        target_dimension=dim_str,
        target_operator=claim.target_operator.value,
        target_threshold=claim.target_value,
        target_units=claim.unit,
        metric_name=metric_name,
        metric_version="1.0.0",
        metric_denominator=metric_denom,
        observed_epistemic_value=evidence,
        verification_verdict=verdict,
        verdict_reason=reason,
        evidence_references=refs,
        limitations_and_assumptions=limitations
    )


def generate_claim_verification_matrix(
    company_id: str,
    claims: List[ClaimSchema],
    evidence_by_dimension: Dict[str, EpistemicValue],
    evidence_refs: Optional[Dict[str, List[EvidenceReference]]] = None,
    min_sample_size: int = 15
) -> ClaimVerificationMatrix:
    """
    Constructs a complete Claim Verification Matrix across all submitted claims.
    """
    matrix_id = f"CVM-{company_id.upper()}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    entries: List[ClaimVerificationMatrixEntry] = []
    
    verdict_counts: Dict[str, int] = {
        VerificationVerdict.VERIFIED.value: 0,
        VerificationVerdict.PARTIALLY_VERIFIED.value: 0,
        VerificationVerdict.CONTRADICTED.value: 0,
        VerificationVerdict.INSUFFICIENT_EVIDENCE.value: 0,
        VerificationVerdict.UNVERIFIED.value: 0
    }

    refs_map = evidence_refs or {}

    for claim in claims:
        dim_key = claim.dimension.value if hasattr(claim.dimension, "value") else str(claim.dimension)
        evidence = evidence_by_dimension.get(dim_key)
        refs = refs_map.get(claim.claim_id, refs_map.get(dim_key, []))
        
        entry = evaluate_single_claim(
            claim=claim,
            evidence=evidence,
            evidence_refs=refs,
            min_sample_size=min_sample_size
        )
        entries.append(entry)
        verdict_counts[entry.verification_verdict.value] = verdict_counts.get(entry.verification_verdict.value, 0) + 1

    summary = {
        "total_claims": len(claims),
        "verified_count": verdict_counts[VerificationVerdict.VERIFIED.value],
        "partially_verified_count": verdict_counts[VerificationVerdict.PARTIALLY_VERIFIED.value],
        "contradicted_count": verdict_counts[VerificationVerdict.CONTRADICTED.value],
        "insufficient_evidence_count": verdict_counts[VerificationVerdict.INSUFFICIENT_EVIDENCE.value],
        "unverified_count": verdict_counts[VerificationVerdict.UNVERIFIED.value],
        "conclusive_claims_rate": (
            (verdict_counts[VerificationVerdict.VERIFIED.value] + verdict_counts[VerificationVerdict.CONTRADICTED.value]) / len(claims)
            if claims else 0.0
        )
    }

    return ClaimVerificationMatrix(
        matrix_id=matrix_id,
        company_id=company_id,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        schema_version="1.0.0",
        entries=entries,
        summary=summary
    )
