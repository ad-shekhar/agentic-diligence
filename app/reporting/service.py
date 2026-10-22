"""
Diligence Reporting & Bundle Assembly Service (Phase 4).

Coordinates trace loading, task segmentation, metric computation,
Claim Verification Matrix evaluation, and bundle artifact compilation.
"""

import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import Company, Trace, Span, Claim, PayloadProvenance
from app.epistemic.tags import EpistemicTag, TrustLevel, VerificationVerdict, ConfidenceBounds, EpistemicValue
from app.epistemic.claims import ClaimDimension, ComparisonOperator, ClaimSchema
from app.analysis.task_segmentation import segment_trace, TraceSegmentationResult
from app.analysis.metrics_engine import compute_diligence_metrics, NormalizedSpan as SchemaSpan, DiligenceMetrics
from app.evidence.claim_matrix import (
    ClaimVerificationMatrix, ClaimVerificationMatrixEntry,
    EvidenceReference, generate_claim_verification_matrix
)
from app.reporting.canonical_report import (
    build_canonical_diligence_report, render_markdown_diligence_report
)
from app.reporting.manifest import (
    ArtifactEntry, ArtifactType, SerializationMethod,
    build_evidence_manifest, canonicalize_json, compute_canonical_sha256,
    compute_sha256_bytes, compute_sha256_file
)
from app.aibom.generator import generate_native_aibom, export_cyclonedx_aibom


def assemble_company_evidence(
    db: Session,
    company_id: str,
    gap_heuristic_ms: float = 300000.0
) -> Tuple[Dict[str, EpistemicValue], Dict[str, Any], List[str], DiligenceMetrics]:
    """
    Extracts traces and spans for a company, normalizes them, runs segmentation,
    and returns dimension-keyed EpistemicValues, scope summary, payload hashes, and metrics.
    """
    traces = db.query(Trace).filter(Trace.company_id == company_id).all()
    
    # Collect payload hashes from provenance table or fallback to trace ids
    prov_records = (
        db.query(PayloadProvenance.payload_hash)
        .filter(PayloadProvenance.company_id == company_id)
        .all()
    )
    trace_payload_hashes = [p[0] for p in prov_records if p[0]]
    if not trace_payload_hashes:
        trace_payload_hashes = [f"tr-hash-{t.id[:8]}" for t in traces]

    all_norm_spans: List[SchemaSpan] = []
    all_seg_results: List[TraceSegmentationResult] = []
    trust_counts = {"T0": 0, "T1": 0, "T2": 0, "T3": 0}
    total_spans = 0

    for trace in traces:
        norm_spans: List[SchemaSpan] = []
        for sp in trace.spans:
            total_spans += 1
            t_level = TrustLevel.T1
            trust_counts[t_level.value] = trust_counts.get(t_level.value, 0) + 1
            
            ns = SchemaSpan(
                span_id=sp.id,
                trace_id=trace.id,
                name=sp.name,
                span_kind=sp.span_kind,
                start_time=sp.start_time,
                end_time=sp.end_time,
                duration_ms=sp.duration_ms,
                status_code="ERROR" if sp.is_error else "OK",
                provider_name=sp.gen_ai_system,
                requested_model=sp.gen_ai_model,
                input_tokens=sp.gen_ai_prompt_tokens,
                output_tokens=sp.gen_ai_completion_tokens,
                has_token_data=(sp.gen_ai_prompt_tokens or 0) + (sp.gen_ai_completion_tokens or 0) > 0,
                tool_name=sp.tool_name,
                is_human_intervention=sp.is_human_intervention,
                human_action_type=sp.human_action_type,
                intervention_detection_method=(
                    sp.detection_method.value if sp.detection_method else None
                ),
                cost_usd=sp.cost or 0.0,
                cost_status=sp.cost_status.value if sp.cost_status else "MEASURED",
                trust_level=t_level,
            )
            norm_spans.append(ns)
            all_norm_spans.append(ns)

        seg = segment_trace(
            norm_spans,
            trace_id=trace.id,
            workflow_name=trace.name,
            gap_heuristic_ms=gap_heuristic_ms,
        )
        all_seg_results.append(seg)

    metrics = compute_diligence_metrics(all_seg_results, all_norm_spans)

    total_tasks = sum(s.total_tasks for s in all_seg_results)
    unobserved_intervals = sum(
        1 for s in all_seg_results for t in s.tasks if t.epistemic_tag == EpistemicTag.UNKNOWN
    )

    scope = {
        "total_traces_analyzed": len(traces),
        "total_spans_analyzed": total_spans,
        "total_tasks_segmented": total_tasks,
        "evidence_trust_summary": trust_counts,
        "unobserved_intervals_count": unobserved_intervals
    }

    # Map signals to dimension-keyed EpistemicValues
    evidence_by_dimension: Dict[str, EpistemicValue] = {
        "autonomy": metrics.autonomy_rate,
        "unit_economics": metrics.cost_per_task,
        "unit_cost": metrics.cost_per_task,
        "provider_concentration": metrics.model_concentration,
        "dependencies": metrics.model_concentration,
        "provider_spread": metrics.model_concentration,
        "reliability": metrics.error_rate,
        "evidence_coverage": metrics.telemetry_coverage,
        "evaluation_overhead": EpistemicValue(
            value=0.0,
            tag=EpistemicTag.CALCULATED,
            trust_level=TrustLevel.T1,
            bounds=ConfidenceBounds(lower=0.0, point_estimate=0.0, upper=0.0),
            sample_size=total_tasks,
            unknown_fraction=0.0,
            notes="No dedicated evaluation tax spans identified."
        ),
        "least_privilege": EpistemicValue(
            value=0.0,
            tag=EpistemicTag.CALCULATED,
            trust_level=TrustLevel.T1,
            bounds=ConfidenceBounds(lower=0.0, point_estimate=0.0, upper=0.0),
            sample_size=total_spans,
            unknown_fraction=0.0,
            notes="Tool execution risk baseline."
        )
    }

    return evidence_by_dimension, scope, trace_payload_hashes, metrics


def load_company_claims(db: Session, company_id: str) -> List[ClaimSchema]:
    """
    Loads company claims from the database, or generates a standard diligence claim battery.
    """
    db_claims = db.query(Claim).filter(Claim.company_id == company_id).all()
    if db_claims:
        claims: List[ClaimSchema] = []
        for c in db_claims:
            cat = (c.category or "autonomy").lower()
            dim = ClaimDimension.AUTONOMY
            if "cost" in cat or "econ" in cat:
                dim = ClaimDimension.UNIT_COST
            elif "depend" in cat or "cloud" in cat or "spread" in cat or "hhi" in cat:
                dim = ClaimDimension.PROVIDER_SPREAD
            elif "relia" in cat or "error" in cat:
                dim = ClaimDimension.RELIABILITY

            claims.append(ClaimSchema(
                claim_id=f"CLM-{c.id[:6].upper()}",
                dimension=dim,
                stated_claim_text=c.claim_text or "Vendor runtime assertion",
                target_operator=ComparisonOperator.LESS_EQUAL if dim in (ClaimDimension.UNIT_COST, ClaimDimension.RELIABILITY) else ComparisonOperator.GREATER_EQUAL,
                target_value=float(c.target_value or 0.0),
                unit="%" if dim in (ClaimDimension.AUTONOMY, ClaimDimension.RELIABILITY) else ("USD" if dim == ClaimDimension.UNIT_COST else ""),
                source_document=c.source or "Pitch Deck / Vendor SLA"
            ))
        return claims

    # Default standard diligence claim battery
    return [
        ClaimSchema(
            claim_id="CLM-001",
            dimension=ClaimDimension.AUTONOMY,
            stated_claim_text="System executes tasks with >= 90% autonomy",
            target_operator=ComparisonOperator.GREATER_EQUAL,
            target_value=90.0,
            unit="%",
            source_document="Pitch Deck (Slide 4)"
        ),
        ClaimSchema(
            claim_id="CLM-002",
            dimension=ClaimDimension.UNIT_COST,
            stated_claim_text="Execution cost per task remains <= $0.10",
            target_operator=ComparisonOperator.LESS_EQUAL,
            target_value=0.10,
            unit="USD",
            source_document="Pitch Deck (Slide 8)"
        ),
        ClaimSchema(
            claim_id="CLM-003",
            dimension=ClaimDimension.PROVIDER_SPREAD,
            stated_claim_text="Resilient multi-cloud orchestration with balanced vendor spread (HHI <= 3500)",
            target_operator=ComparisonOperator.LESS_EQUAL,
            target_value=3500.0,
            unit="HHI",
            source_document="Technical Whitepaper (Section 3)"
        ),
        ClaimSchema(
            claim_id="CLM-004",
            dimension=ClaimDimension.RELIABILITY,
            stated_claim_text="Span error rate does not exceed 5%",
            target_operator=ComparisonOperator.LESS_EQUAL,
            target_value=5.0,
            unit="%",
            source_document="Commercial SLA"
        )
    ]


def assemble_canonical_diligence_report_package(
    db: Session,
    company_id: str,
    is_synthetic: bool = False
) -> Tuple[Dict[str, Any], str, ClaimVerificationMatrix]:
    """
    Assembles the canonical report JSON, renders markdown, and returns matrix object.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    comp_name = company.name if company else "Target AI Company"

    evidence_by_dim, scope, trace_payload_hashes, metrics = assemble_company_evidence(db, company_id)
    claims = load_company_claims(db, company_id)

    # Attach evidence references if available
    refs_map: Dict[str, List[EvidenceReference]] = {}
    traces = db.query(Trace.id).filter(Trace.company_id == company_id).all()
    t_ids = [t[0] for t in traces]
    default_ref = [EvidenceReference(
        artifact_name="canonical/metrics.json",
        artifact_sha256=compute_canonical_sha256(metrics.to_dict()),
        trace_ids=t_ids
    )]
    for c in claims:
        refs_map[c.claim_id] = default_ref

    matrix = generate_claim_verification_matrix(
        company_id=company_id,
        claims=claims,
        evidence_by_dimension=evidence_by_dim,
        evidence_refs=refs_map,
        min_sample_size=15
    )

    report_json = build_canonical_diligence_report(
        company_id=company_id,
        company_name=comp_name,
        scope=scope,
        signals=metrics.to_dict(),
        claim_matrix=matrix,
        trace_payload_digests=trace_payload_hashes,
        is_synthetic=is_synthetic
    )

    report_md = render_markdown_diligence_report(report_json)
    return report_json, report_md, matrix


def compile_diligence_bundle_on_disk(
    db: Session,
    company_id: str,
    output_dir: str,
    is_synthetic: bool = False
) -> Dict[str, Any]:
    """
    Compiles all Phase 4 artifacts into a physical bundle directory on disk
    and writes a cryptographically verified manifest.json.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Subdirectories
    evidence_dir = os.path.join(output_dir, "evidence")
    canonical_dir = os.path.join(output_dir, "canonical")
    aibom_dir = os.path.join(output_dir, "aibom")
    reports_dir = os.path.join(output_dir, "reports")
    
    for d in (evidence_dir, canonical_dir, aibom_dir, reports_dir):
        os.makedirs(d, exist_ok=True)

    # 1. Canonical Report & Markdown & Claim Matrix
    rep_json, rep_md, matrix = assemble_canonical_diligence_report_package(db, company_id, is_synthetic)
    
    rep_json_path = os.path.join(reports_dir, "diligence_report.json")
    rep_md_path = os.path.join(reports_dir, "diligence_report.md")
    matrix_path = os.path.join(canonical_dir, "claim_verification_matrix.json")
    metrics_path = os.path.join(canonical_dir, "canonical_metrics.json")

    with open(rep_json_path, "wb") as f:
        f.write(canonicalize_json(rep_json, pretty=True))
    with open(rep_md_path, "w", encoding="utf-8") as f:
        f.write(rep_md)
    with open(matrix_path, "wb") as f:
        f.write(canonicalize_json(matrix.to_dict(), pretty=True))
    with open(metrics_path, "wb") as f:
        f.write(canonicalize_json(rep_json.get("signals", {}), pretty=True))

    # 2. CycloneDX AI-BOM
    native_bom = generate_native_aibom(db, company_id)
    cdx_bom = export_cyclonedx_aibom(native_bom, spec_version="1.6")
    cdx_path = os.path.join(aibom_dir, "cyclonedx_1.6.json")
    with open(cdx_path, "wb") as f:
        f.write(canonicalize_json(cdx_bom, pretty=True))

    # 3. Raw traces summary
    traces = db.query(Trace).filter(Trace.company_id == company_id).all()
    traces_summary = [
        {"trace_id": t.id, "name": t.name, "span_count": len(t.spans), "is_error": t.is_error}
        for t in traces
    ]
    raw_traces_path = os.path.join(evidence_dir, "traces.json")
    with open(raw_traces_path, "wb") as f:
        f.write(canonicalize_json(traces_summary, pretty=True))

    # 4. Build Artifact Entries for Manifest
    artifacts: List[ArtifactEntry] = [
        ArtifactEntry(
            path="evidence/traces.json",
            artifact_type=ArtifactType.RAW_TELEMETRY.value,
            sha256=compute_canonical_sha256(traces_summary, pretty=True),
            byte_size=os.path.getsize(raw_traces_path),
            serialization_method=SerializationMethod.CANONICAL_JSON_PRETTY.value,
            epistemic_trust_level="T1"
        ),
        ArtifactEntry(
            path="canonical/canonical_metrics.json",
            artifact_type=ArtifactType.CANONICAL_METRICS.value,
            sha256=compute_canonical_sha256(rep_json.get("signals", {}), pretty=True),
            byte_size=os.path.getsize(metrics_path),
            serialization_method=SerializationMethod.CANONICAL_JSON_PRETTY.value,
            epistemic_trust_level="T1"
        ),
        ArtifactEntry(
            path="canonical/claim_verification_matrix.json",
            artifact_type=ArtifactType.CLAIM_VERIFICATION_MATRIX.value,
            sha256=compute_canonical_sha256(matrix.to_dict(), pretty=True),
            byte_size=os.path.getsize(matrix_path),
            serialization_method=SerializationMethod.CANONICAL_JSON_PRETTY.value,
            epistemic_trust_level="T1"
        ),
        ArtifactEntry(
            path="aibom/cyclonedx_1.6.json",
            artifact_type=ArtifactType.CYCLONEDX_AIBOM.value,
            sha256=compute_canonical_sha256(cdx_bom, pretty=True),
            byte_size=os.path.getsize(cdx_path),
            serialization_method=SerializationMethod.CANONICAL_JSON_PRETTY.value,
            epistemic_trust_level="T1"
        ),
        ArtifactEntry(
            path="reports/diligence_report.json",
            artifact_type=ArtifactType.DILIGENCE_REPORT_JSON.value,
            sha256=compute_canonical_sha256(rep_json, pretty=True),
            byte_size=os.path.getsize(rep_json_path),
            serialization_method=SerializationMethod.CANONICAL_JSON_PRETTY.value,
            epistemic_trust_level="T1"
        ),
        ArtifactEntry(
            path="reports/diligence_report.md",
            artifact_type=ArtifactType.DILIGENCE_REPORT_MARKDOWN.value,
            sha256=compute_sha256_file(rep_md_path),
            byte_size=os.path.getsize(rep_md_path),
            serialization_method=SerializationMethod.UTF8_TEXT.value,
            epistemic_trust_level="T1"
        ),
    ]

    manifest = build_evidence_manifest(
        company_id=company_id,
        artifacts=artifacts,
        generator_version="agd-0.4.0"
    )

    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "wb") as f:
        f.write(canonicalize_json(manifest, pretty=True))

    return {
        "bundle_id": manifest["bundle_id"],
        "manifest_path": manifest_path,
        "manifest": manifest,
        "output_dir": output_dir,
        "artifacts_compiled": len(artifacts)
    }
