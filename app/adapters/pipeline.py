"""
Unified Evidence Ingestion & Verification Pipeline (Phase 6 â€” Milestone C).

Connects multi-source adapters (OTLP, MCP, Browser), the UnifiedEvidenceRegistry,
and the EvidenceCorrelationEngine to the ClaimVerificationMatrix and DiligenceMetrics engines.

Maintains strict epistemic boundaries:
1. Never treat missing evidence as proof that an action occurred or did not occur.
2. Unresolved MCP tool calls remain UNKNOWN; they never collapse into successful execution.
3. Browser approval modals remain HUMAN_EXPLICIT; they never collapse into autonomous execution.
4. Telemetry gaps > 35% trigger INSUFFICIENT_EVIDENCE.
5. Preserves end-to-end cryptographic provenance hashes and audit references.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from sqlalchemy.orm import Session

from app.adapters.base import ProvenanceEnvelope
from app.adapters.registry import (
    EvidenceRecord,
    EvidenceStatus,
    IngestionReceipt,
    SourceType,
    UnifiedEvidenceRegistry,
    default_registry,
)
from app.adapters.correlation import (
    AnomalyType,
    CorrelationAnomaly,
    CorrelatedTrace,
    EvidenceCorrelationEngine,
    default_correlation_engine,
)
from app.analysis.metrics_engine import DiligenceMetrics, compute_diligence_metrics
from app.analysis.task_segmentation import (
    TraceSegmentationResult,
    segment_trace,
)
from app.epistemic.claims import (
    ClaimDimension,
    ClaimSchema,
    ComparisonOperator,
)
from app.epistemic.tags import (
    ConfidenceBounds,
    EpistemicTag,
    EpistemicValue,
    TrustLevel,
    VerificationVerdict,
)
from app.evidence.claim_matrix import (
    ClaimVerificationMatrix,
    ClaimVerificationMatrixEntry,
    EvidenceReference,
    evaluate_single_claim,
)
from app.ingestion.schema import NormalizedSpan


@dataclass
class VerificationPipelineResult:
    """Consolidated end-to-end audit result produced by the UnifiedVerificationPipeline."""
    pipeline_version: str
    company_id: str
    generated_at_utc: str
    total_evidence_records: int
    total_correlated_traces: int
    total_spans: int
    metrics: DiligenceMetrics
    matrix: ClaimVerificationMatrix
    anomalies: List[CorrelationAnomaly]
    provenance_envelopes: List[ProvenanceEnvelope]
    summary: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_version": self.pipeline_version,
            "company_id": self.company_id,
            "generated_at_utc": self.generated_at_utc,
            "total_evidence_records": self.total_evidence_records,
            "total_correlated_traces": self.total_correlated_traces,
            "total_spans": self.total_spans,
            "metrics": self.metrics.to_dict(),
            "matrix": self.matrix.to_dict(),
            "anomalies": [a.to_dict() for a in self.anomalies],
            "provenance_envelopes": [e.to_dict() for e in self.provenance_envelopes],
            "summary": self.summary,
        }


class UnifiedVerificationPipeline:
    """
    End-to-end pipeline coordinating ingestion, correlation, task segmentation,
    metrics calculation, and formal claim verification.
    """

    PIPELINE_VERSION = "v1.6.0"

    def __init__(
        self,
        registry: Optional[UnifiedEvidenceRegistry] = None,
        correlation_engine: Optional[EvidenceCorrelationEngine] = None,
    ):
        self.registry = registry or default_registry
        self.correlation_engine = correlation_engine or default_correlation_engine

    def ingest_evidence(
        self,
        raw_bytes: bytes,
        source_type: Optional[Union[SourceType, str]] = None,
        company_id: Optional[str] = None,
        content_type: str = "application/json",
        provenance_hash: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> IngestionReceipt:
        """
        Directly registers raw evidence payload into the unified evidence registry.
        Enforces idempotency, calculates SHA-256 digests, and validates syntax.
        """
        return self.registry.register_payload(
            raw_bytes=raw_bytes,
            source_type=source_type,
            content_type=content_type,
            company_id=company_id,
            provenance_hash=provenance_hash,
            db=db,
        )

    def verify_claims(
        self,
        claims: Sequence[ClaimSchema],
        company_id: Optional[str] = None,
        min_sample_size: int = 15,
        db: Optional[Session] = None,
    ) -> VerificationPipelineResult:
        """
        Runs full verification across all registered evidence for the specified company.
        Correlates multi-source records, computes metrics, and produces explainable verdicts.
        """
        effective_company_id = company_id or "default_target"
        records = self.registry.get_records(company_id=effective_company_id, include_duplicates=False, db=db)
        envelopes = self.registry.get_provenance_envelopes(company_id=effective_company_id, db=db)

        now_iso = datetime.now(timezone.utc).isoformat()

        # Handle zero evidence case defensively
        if not records:
            empty_entries = []
            for claim in claims:
                empty_val = EpistemicValue(
                    value=None,
                    tag=EpistemicTag.UNKNOWN,
                    trust_level=TrustLevel.T0,
                    bounds=None,
                    sample_size=0,
                    unknown_fraction=1.0,
                    notes=["No telemetry records registered for scope."]
                )
                entry = evaluate_single_claim(claim, empty_val, min_sample_size=min_sample_size)
                empty_entries.append(entry)

            empty_metrics = DiligenceMetrics(
                autonomy_rate=EpistemicValue(value=None, tag=EpistemicTag.UNKNOWN, trust_level=TrustLevel.T0, bounds=None, sample_size=0, unknown_fraction=1.0),
                human_intervention_rate=EpistemicValue(value=None, tag=EpistemicTag.UNKNOWN, trust_level=TrustLevel.T0, bounds=None, sample_size=0, unknown_fraction=1.0),
                task_completion_rate=EpistemicValue(value=None, tag=EpistemicTag.UNKNOWN, trust_level=TrustLevel.T0, bounds=None, sample_size=0, unknown_fraction=1.0),
                error_rate=EpistemicValue(value=None, tag=EpistemicTag.UNKNOWN, trust_level=TrustLevel.T0, bounds=None, sample_size=0, unknown_fraction=1.0),
                token_efficiency=EpistemicValue(value=None, tag=EpistemicTag.UNKNOWN, trust_level=TrustLevel.T0, bounds=None, sample_size=0, unknown_fraction=1.0),
                cost_per_task=EpistemicValue(value=None, tag=EpistemicTag.UNKNOWN, trust_level=TrustLevel.T0, bounds=None, sample_size=0, unknown_fraction=1.0),
                model_concentration=EpistemicValue(value=None, tag=EpistemicTag.UNKNOWN, trust_level=TrustLevel.T0, bounds=None, sample_size=0, unknown_fraction=1.0),
                telemetry_coverage=EpistemicValue(value=None, tag=EpistemicTag.UNKNOWN, trust_level=TrustLevel.T0, bounds=None, sample_size=0, unknown_fraction=1.0),
                computation_notes=["Zero evidence ingested."]
            )

            matrix = ClaimVerificationMatrix(
                matrix_id=f"matrix-{effective_company_id}-{int(datetime.now(timezone.utc).timestamp())}",
                company_id=effective_company_id,
                generated_at_utc=now_iso,
                entries=empty_entries,
                summary={
                    "total_claims": len(claims),
                    "verified": 0,
                    "partially_verified": 0,
                    "contradicted": 0,
                    "insufficient_evidence": len(claims),
                }
            )

            return VerificationPipelineResult(
                pipeline_version=self.PIPELINE_VERSION,
                company_id=effective_company_id,
                generated_at_utc=now_iso,
                total_evidence_records=0,
                total_correlated_traces=0,
                total_spans=0,
                metrics=empty_metrics,
                matrix=matrix,
                anomalies=[],
                provenance_envelopes=envelopes,
                summary=matrix.summary,
            )

        # 1. Multi-source correlation
        correlated_traces = self.correlation_engine.correlate_records(records, filter_duplicates=True)

        all_anomalies: List[CorrelationAnomaly] = []
        for ct in correlated_traces:
            all_anomalies.extend(ct.anomalies)

        # 2. Trace segmentation over correlated spans
        segmentation_results: List[TraceSegmentationResult] = []
        all_correlated_spans: List[NormalizedSpan] = []

        for ct in correlated_traces:
            seg = segment_trace(ct.spans, trace_id=ct.trace_id)
            segmentation_results.append(seg)
            all_correlated_spans.extend(ct.spans)

        # 3. Deterministic diligence metrics calculation
        metrics = compute_diligence_metrics(segmentation_results, all_correlated_spans)

        # 4. Construct cryptographic evidence references
        all_trace_ids = sorted(list({ct.trace_id for ct in correlated_traces}))
        evidence_refs: List[EvidenceReference] = []
        for env in envelopes:
            evidence_refs.append(EvidenceReference(
                artifact_name=f"envelope_{env.adapter_id}_{effective_company_id}",
                artifact_sha256=env.payload_sha256,
                trace_ids=all_trace_ids,
            ))

        # 5. Map dimension signals to EpistemicValues
        dim_evidence: Dict[ClaimDimension, EpistemicValue] = {
            ClaimDimension.AUTONOMY: metrics.autonomy_rate,
            ClaimDimension.UNIT_COST: metrics.cost_per_task,
            ClaimDimension.PROVIDER_SPREAD: metrics.model_concentration,
            ClaimDimension.DEPENDENCIES: metrics.model_concentration,
            ClaimDimension.RELIABILITY: metrics.error_rate,
            ClaimDimension.EVIDENCE_COVERAGE: metrics.telemetry_coverage,
        }

        # 6. Evaluate claims against empirical evidence
        matrix_entries: List[ClaimVerificationMatrixEntry] = []
        verified_count = 0
        partially_verified_count = 0
        contradicted_count = 0
        insufficient_count = 0

        # Collect any contradiction notes from correlation
        contradiction_descriptions = [
            a.description for a in all_anomalies if a.anomaly_type == AnomalyType.CONTRADICTORY_OBSERVATION
        ]

        for claim in claims:
            ev = dim_evidence.get(claim.dimension)
            entry = evaluate_single_claim(
                claim=claim,
                evidence=ev,
                evidence_refs=evidence_refs,
                min_sample_size=min_sample_size,
            )

            # Surface cross-source contradictions if relevant to this dimension
            if contradiction_descriptions:
                if claim.dimension == ClaimDimension.AUTONOMY:
                    for desc in contradiction_descriptions:
                        if "human intervention" in desc.lower() or "modal" in desc.lower():
                            entry.limitations_and_assumptions.append(desc)
                elif claim.dimension == ClaimDimension.RELIABILITY:
                    for desc in contradiction_descriptions:
                        if "downgrading to error" in desc.lower() or "t2 mcp" in desc.lower():
                            entry.limitations_and_assumptions.append(desc)

            # Count verdicts
            v = entry.verification_verdict
            if v == VerificationVerdict.VERIFIED:
                verified_count += 1
            elif v == VerificationVerdict.PARTIALLY_VERIFIED:
                partially_verified_count += 1
            elif v == VerificationVerdict.CONTRADICTED:
                contradicted_count += 1
            else:
                insufficient_count += 1

            matrix_entries.append(entry)

        summary = {
            "total_claims": len(claims),
            "verified": verified_count,
            "partially_verified": partially_verified_count,
            "contradicted": contradicted_count,
            "insufficient_evidence": insufficient_count,
            "total_anomalies_detected": len(all_anomalies),
            "contradictions_detected": len(contradiction_descriptions),
            "dark_zones_detected": len([a for a in all_anomalies if a.anomaly_type == AnomalyType.DARK_ZONE_GAP]),
        }

        matrix = ClaimVerificationMatrix(
            matrix_id=f"matrix-{effective_company_id}-{int(datetime.now(timezone.utc).timestamp())}",
            company_id=effective_company_id,
            generated_at_utc=now_iso,
            entries=matrix_entries,
            summary=summary,
        )

        return VerificationPipelineResult(
            pipeline_version=self.PIPELINE_VERSION,
            company_id=effective_company_id,
            generated_at_utc=now_iso,
            total_evidence_records=len(records),
            total_correlated_traces=len(correlated_traces),
            total_spans=len(all_correlated_spans),
            metrics=metrics,
            matrix=matrix,
            anomalies=all_anomalies,
            provenance_envelopes=envelopes,
            summary=summary,
        )


# Singleton instance
default_pipeline = UnifiedVerificationPipeline()
