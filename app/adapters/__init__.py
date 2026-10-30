"""
Evidence Adapters Package (Phase 5).

Provides multi-source evidence adapters conforming to docs/phase-5/evidence-adapter-architecture.md.
"""

from app.adapters.base import (
    AdapterCapability,
    ProvenanceEnvelope,
    BaseEvidenceAdapter,
)
from app.adapters.otlp import (
    OtlpEvidenceAdapter,
)
from app.adapters.mcp import (
    McpEvidenceAdapter,
    McpLifecycleState,
)
from app.adapters.browser import (
    BrowserEvidenceAdapter,
    BrowserActionType,
)
from app.adapters.pilot import (
    PilotScenarioType,
    PilotEvaluationReport,
    run_ground_truth_pilot,
)

__all__ = [
    "AdapterCapability",
    "ProvenanceEnvelope",
    "BaseEvidenceAdapter",
    "OtlpEvidenceAdapter",
    "McpEvidenceAdapter",
    "McpLifecycleState",
    "BrowserEvidenceAdapter",
    "BrowserActionType",
    "PilotScenarioType",
    "PilotEvaluationReport",
    "run_ground_truth_pilot",
]
