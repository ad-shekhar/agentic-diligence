from typing import Dict, Any, Tuple
from app.db.models import VerificationStatus, ConfidenceLevel

def verify_autonomy_claim(claimed_text: str, target_pct: float, observed_pct: float, sample_size: int) -> Tuple[VerificationStatus, str, ConfidenceLevel]:
    """
    Evaluates pitch deck autonomy claim against observed telemetry metrics deterministically.
    """
    if sample_size < 15:
        return (
            VerificationStatus.INSUFFICIENT_EVIDENCE,
            f"Sample size of {sample_size} traces is insufficient (minimum: 15) to establish verification status for autonomy claims.",
            ConfidenceLevel.UNVERIFIED
        )
        
    diff = observed_pct - target_pct
    
    if diff >= -2.0:
        return (
            VerificationStatus.VERIFIED,
            f"Observed autonomous workflow completion rate of {observed_pct:.1f}% meets or exceeds the stated target of {target_pct:.1f}%.",
            ConfidenceLevel.HIGH
        )
    elif diff >= -25.0:
        return (
            VerificationStatus.PARTIALLY_VERIFIED,
            f"Observed autonomous rate of {observed_pct:.1f}% is {abs(diff):.1f} percentage points below the stated claim of {target_pct:.1f}%. Human intervention was observed in {100.0 - observed_pct:.1f}% of traces.",
            ConfidenceLevel.HIGH
        )
    else:
        return (
            VerificationStatus.CONTRADICTED,
            f"Observed autonomous rate of {observed_pct:.1f}% is significantly below the stated claim of {target_pct:.1f}%. Human intervention was required in {100.0 - observed_pct:.1f}% of observed traces.",
            ConfidenceLevel.HIGH
        )

def verify_economics_claim(claimed_text: str, claimed_cost: float, observed_cost: float, sample_size: int) -> Tuple[VerificationStatus, str, ConfidenceLevel]:
    """
    Evaluates pitch deck cost claim against observed telemetry-attributable execution cost deterministically.
    """
    if sample_size < 15:
        return (
            VerificationStatus.INSUFFICIENT_EVIDENCE,
            f"Sample size of {sample_size} tasks is insufficient (minimum: 15) to verify unit economics claims.",
            ConfidenceLevel.UNVERIFIED
        )
        
    ratio = observed_cost / claimed_cost if claimed_cost > 0 else 1.0
    
    if ratio <= 1.1:
        return (
            VerificationStatus.VERIFIED,
            f"Observed telemetry-attributable cost of ${observed_cost:.4f}/task aligns with the claimed target of ${claimed_cost:.4f}/task.",
            ConfidenceLevel.HIGH
        )
    elif ratio <= 2.5:
        return (
            VerificationStatus.PARTIALLY_VERIFIED,
            f"Observed telemetry-attributable cost of ${observed_cost:.4f}/task exceeds the claimed target of ${claimed_cost:.4f}/task by {ratio:.1f}x.",
            ConfidenceLevel.HIGH
        )
    else:
        return (
            VerificationStatus.CONTRADICTED,
            f"Observed telemetry-attributable cost of ${observed_cost:.4f}/task is {ratio:.1f}x higher than the claimed cost of ${claimed_cost:.4f}/task.",
            ConfidenceLevel.HIGH
        )

def verify_dependency_claim(claimed_text: str, hhi_score: float, primary_share_pct: float) -> Tuple[VerificationStatus, str, ConfidenceLevel]:
    """
    Evaluates pitch deck multi-cloud resilience claim against provider concentration metrics deterministically.

    HHI is on the 0–10,000 scale (matching metrics_engine._compute_hhi()):
      - HHI >= 8000 or primary share >= 90% → CONTRADICTED (single-provider dominance)
      - HHI >= 3500 or primary share >= 60% → PARTIALLY_VERIFIED (concentrated but multi-provider)
      - Otherwise → VERIFIED (balanced multi-provider architecture)
    """
    if primary_share_pct >= 90.0 or hhi_score >= 8000.0:
        return (
            VerificationStatus.CONTRADICTED,
            f"Telemetry shows primary provider represents {primary_share_pct:.1f}% of cost/traffic (HHI: {hhi_score:.0f}/10000), which does not support the multi-cloud resilient orchestration claim.",
            ConfidenceLevel.HIGH
        )
    elif primary_share_pct >= 60.0 or hhi_score >= 3500.0:
        return (
            VerificationStatus.PARTIALLY_VERIFIED,
            f"Telemetry indicates multi-provider usage, but expenditure remains concentrated with a primary provider ({primary_share_pct:.1f}% share, HHI: {hhi_score:.0f}/10000).",
            ConfidenceLevel.HIGH
        )
    else:
        return (
            VerificationStatus.VERIFIED,
            f"Telemetry confirms balanced multi-provider architecture (primary provider share: {primary_share_pct:.1f}%, HHI: {hhi_score:.0f}/10000).",
            ConfidenceLevel.HIGH
        )
