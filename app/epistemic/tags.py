"""
Epistemic Tagging Taxonomy and Trust Ladder for Agentic Diligence.
Enforces that every metric, observation, and claim verification carries
an explicit epistemic tag, trust level, and uncertainty bounds.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple, Any, Dict

class EpistemicTag(str, Enum):
    """
    Mutually exclusive epistemic tags categorizing the source and nature of data.
    """
    OBSERVED = "[OBSERVED]"     # Directly recorded in telemetry spans (e.g. token counts, exit codes)
    CALCULATED = "[CALCULATED]" # Derived deterministically via published mathematical formulas
    INFERRED = "[INFERRED]"     # Heuristic classification, explicitly labeled and never isolated
    UNKNOWN = "[UNKNOWN]"       # Uninstrumented intervals or missing spans; never silently assumed

class TrustLevel(str, Enum):
    """
    Evidence Trust Ladder (T0 -> T3) reflecting evidentiary assurance.
    """
    T0 = "T0"  # Self-Reported (pitch decks, questionnaires; cannot independently verify claims)
    T1 = "T1"  # In-Process SDK (embedded OpenTelemetry SDK; high granularity, subject to host-trust limits)
    T2 = "T2"  # Independent Proxy (out-of-band observe-only proxy within its interception boundary)
    T3 = "T3"  # Billing Reconciled (cross-matched with immutable external provider billing records)

    @property
    def rank(self) -> int:
        ranks = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}
        return ranks.get(self.value, 0)

    def satisfies_minimum(self, minimum_required: "TrustLevel") -> bool:
        return self.rank >= minimum_required.rank

class VerificationVerdict(str, Enum):
    """
    Deterministic verification verdict for stated claims.
    """
    VERIFIED = "VERIFIED"                       # Stated claim is supported by observed bounds
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"   # Stated claim is within reasonable pre-declared tolerance
    CONTRADICTED = "CONTRADICTED"               # Runtime evidence mathematically conflicts with claim
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE" # Missing data, low sample size, or unknown interval dominates

@dataclass(frozen=True)
class ConfidenceBounds:
    """
    Mathematical uncertainty bounds.
    When uninstrumented or unknown intervals occur, bounds widen rather than
    speculatively collapsing into a single true/false number.
    """
    lower: float
    point_estimate: float
    upper: float

    def __post_init__(self):
        if self.lower > self.upper:
            object.__setattr__(self, "lower", min(self.lower, self.upper))
            object.__setattr__(self, "upper", max(self.lower, self.upper))

    @property
    def spread(self) -> float:
        return self.upper - self.lower

    def to_dict(self) -> Dict[str, float]:
        return {
            "lower": round(self.lower, 4),
            "point_estimate": round(self.point_estimate, 4),
            "upper": round(self.upper, 4),
            "spread": round(self.spread, 4)
        }

@dataclass
class EpistemicValue:
    """
    A measured or calculated value with strict epistemic attribution.
    """
    value: Any
    tag: EpistemicTag
    trust_level: TrustLevel
    bounds: Optional[ConfidenceBounds] = None
    sample_size: int = 0
    unknown_fraction: float = 0.0
    notes: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "epistemic_tag": self.tag.value,
            "trust_level": self.trust_level.value,
            "bounds": self.bounds.to_dict() if self.bounds else None,
            "sample_size": self.sample_size,
            "unknown_fraction_pct": round(self.unknown_fraction * 100.0, 2),
            "notes": self.notes,
            "metadata": self.metadata
        }

def compute_autonomy_bounds(
    autonomous_count: int,
    human_explicit_count: int,
    human_inferred_count: int,
    unknown_count: int
) -> Tuple[ConfidenceBounds, float]:
    """
    Computes strict mathematical autonomy bounds adhering to:
    'Absence of evidence != evidence of absence'.

    - Lower bound (pessimistic): Unknown tasks are treated as non-autonomous.
    - Upper bound (optimistic): Unknown tasks are assumed to have succeeded autonomously.
    - Point estimate: Observed autonomous count over total verified tasks.
    """
    total = autonomous_count + human_explicit_count + human_inferred_count + unknown_count
    if total <= 0:
        return ConfidenceBounds(lower=0.0, point_estimate=0.0, upper=0.0), 0.0

    lower_pct = (autonomous_count / float(total)) * 100.0
    upper_pct = ((autonomous_count + unknown_count) / float(total)) * 100.0
    point_est = lower_pct  # Honest baseline defaults to lower bound

    unknown_frac = unknown_count / float(total)
    return ConfidenceBounds(lower=lower_pct, point_estimate=point_est, upper=upper_pct), unknown_frac
