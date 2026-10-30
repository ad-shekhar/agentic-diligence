"""
Evidence Adapters Package (Phase 5 & 6).

Provides multi-source evidence adapters and the Unified Evidence Registry conforming to
docs/phase-5/evidence-adapter-architecture.md.
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
from app.adapters.registry import (
    SourceType,
    EvidenceStatus,
    EvidenceRecord,
    IngestionReceipt,
    UnifiedEvidenceRegistry,
    default_registry,
    compute_deterministic_evidence_id,
)
from app.adapters.correlation import (
    AnomalyType,
    CorrelationAnomaly,
    CorrelatedToolCall,
    CorrelatedTrace,
    EvidenceCorrelationEngine,
    default_correlation_engine,
)
from app.adapters.pipeline import (
    VerificationPipelineResult,
    UnifiedVerificationPipeline,
    default_pipeline,
)
from app.adapters.benchmarks import (
    Phase6BenchmarkReport,
    run_phase6_benchmarks,
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
    "SourceType",
    "EvidenceStatus",
    "EvidenceRecord",
    "IngestionReceipt",
    "UnifiedEvidenceRegistry",
    "default_registry",
    "compute_deterministic_evidence_id",
    "AnomalyType",
    "CorrelationAnomaly",
    "CorrelatedToolCall",
    "CorrelatedTrace",
    "EvidenceCorrelationEngine",
    "default_correlation_engine",
    "VerificationPipelineResult",
    "UnifiedVerificationPipeline",
    "default_pipeline",
    "Phase6BenchmarkReport",
    "run_phase6_benchmarks",
]
