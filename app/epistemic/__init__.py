"""
Agentic Diligence Epistemic Foundation Package.
"""

from app.epistemic.tags import (
    EpistemicTag,
    TrustLevel,
    VerificationVerdict,
    ConfidenceBounds,
    EpistemicValue,
    compute_autonomy_bounds
)
from app.epistemic.claims import (
    ClaimDimension,
    ComparisonOperator,
    ClaimSchema,
    ClaimVerificationResult,
    verify_claim_against_evidence
)

__all__ = [
    "EpistemicTag",
    "TrustLevel",
    "VerificationVerdict",
    "ConfidenceBounds",
    "EpistemicValue",
    "compute_autonomy_bounds",
    "ClaimDimension",
    "ComparisonOperator",
    "ClaimSchema",
    "ClaimVerificationResult",
    "verify_claim_against_evidence"
]
