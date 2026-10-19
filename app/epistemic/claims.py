"""
Formal Claim Schema and Deterministic Verification Engine.
Evaluates vendor claims against runtime EpistemicValues without subjective LLM-as-judge scoring.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any, Dict, List
from app.epistemic.tags import (
    EpistemicTag, TrustLevel, VerificationVerdict,
    ConfidenceBounds, EpistemicValue
)

class ClaimDimension(str, Enum):
    AUTONOMY = "autonomy"
    UNIT_COST = "unit_cost"
    EVAL_COST = "eval_cost"
    PROVIDER_SPREAD = "provider_spread"
    DEPENDENCIES = "dependencies"
    LEAST_PRIVILEGE = "least_privilege"
    RELIABILITY = "reliability"
    EVIDENCE_COVERAGE = "evidence_coverage"

class ComparisonOperator(str, Enum):
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="
    EQUAL = "=="
    NOT_EQUAL = "!="

@dataclass
class ClaimSchema:
    """
    Formal specification of a performance or architectural claim.
    """
    claim_id: str
    dimension: ClaimDimension
    stated_claim_text: str
    target_operator: ComparisonOperator
    target_value: float
    unit: str
    evidence_trust_minimum: TrustLevel = TrustLevel.T1
    source_document: str = "Pitch Deck / Vendor SLA"
    tolerance_pct: float = 5.0  # Allowable margin of deviation for PARTIALLY_VERIFIED
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "dimension": self.dimension.value,
            "stated_claim_text": self.stated_claim_text,
            "target_operator": self.target_operator.value,
            "target_value": self.target_value,
            "unit": self.unit,
            "evidence_trust_minimum": self.evidence_trust_minimum.value,
            "source_document": self.source_document,
            "tolerance_pct": self.tolerance_pct,
            "notes": self.notes
        }

@dataclass
class ClaimVerificationResult:
    """
    Audit-grade verification result containing evidence references and bounds.
    """
    claim: ClaimSchema
    verdict: VerificationVerdict
    epistemic_evidence: EpistemicValue
    reasoning: str
    discrepancy: Optional[float] = None
    unknown_impact_statement: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim.claim_id,
            "dimension": self.claim.dimension.value,
            "stated_claim": f"{self.claim.stated_claim_text} ({self.claim.target_operator.value} {self.claim.target_value} {self.claim.unit})",
            "verdict": self.verdict.value,
            "epistemic_status": self.epistemic_evidence.tag.value,
            "trust_level": self.epistemic_evidence.trust_level.value,
            "observed_value": self.epistemic_evidence.value,
            "bounds": self.epistemic_evidence.bounds.to_dict() if self.epistemic_evidence.bounds else None,
            "discrepancy": round(self.discrepancy, 4) if self.discrepancy is not None else None,
            "reasoning": self.reasoning,
            "unknown_fraction_pct": round(self.epistemic_evidence.unknown_fraction * 100.0, 2),
            "unknown_impact_statement": self.unknown_impact_statement
        }

def verify_claim_against_evidence(
    claim: ClaimSchema,
    evidence: EpistemicValue,
    min_sample_size: int = 15
) -> ClaimVerificationResult:
    """
    Deterministically evaluates a ClaimSchema against an EpistemicValue.
    Adheres strictly to the principle:
    - Minimum trust level must be satisfied.
    - Low sample sizes result in INSUFFICIENT_EVIDENCE.
    - Excessive unknown intervals result in INSUFFICIENT_EVIDENCE.
    - Contradictions are mathematically proved via bounds and tolerance thresholds.
    """
    # 1. Trust Ladder Requirement Check
    if not evidence.trust_level.satisfies_minimum(claim.evidence_trust_minimum):
        return ClaimVerificationResult(
            claim=claim,
            verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
            epistemic_evidence=evidence,
            reasoning=(
                f"Evidence trust level {evidence.trust_level.value} does not meet the "
                f"required minimum trust level {claim.evidence_trust_minimum.value} for claim {claim.claim_id}. "
                f"Self-reports alone cannot independently verify runtime claims."
            ),
            unknown_impact_statement="Trust level inadequate."
        )

    # 2. Sample Size Check
    if evidence.sample_size < min_sample_size:
        return ClaimVerificationResult(
            claim=claim,
            verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
            epistemic_evidence=evidence,
            reasoning=(
                f"Sample size of {evidence.sample_size} tasks is insufficient to verify claim "
                f"(minimum threshold: {min_sample_size} instrumented tasks)."
            ),
            unknown_impact_statement=f"Sample size {evidence.sample_size} < {min_sample_size}."
        )

    # 3. Unknown Interval Impact Check
    # If more than 35% of tasks or runtime is UNKNOWN, evidence is too ambiguous to claim verification
    if evidence.unknown_fraction > 0.35:
        return ClaimVerificationResult(
            claim=claim,
            verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
            epistemic_evidence=evidence,
            reasoning=(
                f"Uninstrumented intervals represent {evidence.unknown_fraction*100:.1f}% of total task volume. "
                f"Per epistemic rules, missing telemetry produces explicit unknowns rather than assumed success, "
                f"preventing conclusive verification."
            ),
            unknown_impact_statement=f"Excessive uninstrumented dark zones ({evidence.unknown_fraction*100:.1f}% unknown)."
        )

    # 4. Numeric Bounds Evaluation
    bounds = evidence.bounds or ConfidenceBounds(lower=evidence.value, point_estimate=evidence.value, upper=evidence.value)
    target = claim.target_value
    op = claim.target_operator
    tol = claim.tolerance_pct

    # Determine discrepancy
    # For >= claims, negative diff means lower than target
    # For <= claims, positive diff means higher (worse) than target
    if op == ComparisonOperator.GREATER_EQUAL:
        observed_bound = bounds.lower
        diff = observed_bound - target
        
        if diff >= 0:
            verdict = VerificationVerdict.VERIFIED
            reasoning = f"Observed lower bound of {observed_bound:.2f} {claim.unit} meets or exceeds target of {target:.2f} {claim.unit}."
        elif abs(diff) <= tol:
            verdict = VerificationVerdict.PARTIALLY_VERIFIED
            reasoning = f"Observed lower bound of {observed_bound:.2f} {claim.unit} is within allowable tolerance margin of {tol:.1f}% from stated target {target:.2f}."
        else:
            verdict = VerificationVerdict.CONTRADICTED
            reasoning = f"Observed lower bound of {observed_bound:.2f} {claim.unit} falls significantly below stated target of {target:.2f} {claim.unit} (shortfall: {abs(diff):.2f})."
            
    elif op == ComparisonOperator.LESS_EQUAL:
        observed_bound = bounds.upper
        diff = observed_bound - target
        
        if diff <= 0:
            verdict = VerificationVerdict.VERIFIED
            reasoning = f"Observed upper bound of {observed_bound:.4f} {claim.unit} is within target threshold of {target:.4f} {claim.unit}."
        elif target > 0 and (diff / target) * 100.0 <= tol:
            verdict = VerificationVerdict.PARTIALLY_VERIFIED
            reasoning = f"Observed upper bound of {observed_bound:.4f} {claim.unit} exceeds target by only {(diff/target)*100.0:.1f}%, within tolerance {tol:.1f}%."
        else:
            ratio = (observed_bound / target) if target > 0 else 1.0
            verdict = VerificationVerdict.CONTRADICTED
            reasoning = f"Observed cost/metric upper bound of {observed_bound:.4f} {claim.unit} exceeds target of {target:.4f} by {ratio:.2f}x."

    else:
        # Generic equality comparison
        diff = abs(bounds.point_estimate - target)
        if diff == 0:
            verdict = VerificationVerdict.VERIFIED
            reasoning = f"Observed value exactly matches target {target}."
        else:
            verdict = VerificationVerdict.CONTRADICTED
            reasoning = f"Observed value {bounds.point_estimate} differs from target {target}."

    unknown_stmt = None
    if evidence.unknown_fraction > 0:
        unknown_stmt = (
            f"{evidence.unknown_fraction*100:.1f}% of observed volume was uninstrumented [UNKNOWN]. "
            f"Bounds span from {bounds.lower:.2f} to {bounds.upper:.2f} {claim.unit}."
        )

    return ClaimVerificationResult(
        claim=claim,
        verdict=verdict,
        epistemic_evidence=evidence,
        reasoning=reasoning,
        discrepancy=diff,
        unknown_impact_statement=unknown_stmt
    )
