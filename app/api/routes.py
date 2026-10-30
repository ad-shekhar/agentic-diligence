import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional

from app.db.session import get_db
from app.db.models import Company, Tenant, Claim, Report
from app.ingestion.otel import process_otlp_payload
from app.ingestion.synthetic import generate_synthetic_scenario
from app.analysis.intervention import analyze_human_intervention
from app.analysis.economics import analyze_unit_economics
from app.analysis.dependency import analyze_provider_dependencies
from app.analysis.cascade import analyze_failure_cascades
from app.analysis.tool_risk import analyze_tool_execution_risk
from app.analysis.comparison import compare_diligence_targets
from app.analysis.defensibility import analyze_defensibility_and_moat
from app.analysis.stress_test import simulate_stress_test_economics
from app.analysis.memo import generate_investment_committee_memo
from app.reporting.bundle import create_diligence_bundle, verify_diligence_bundle
from app.aibom.generator import generate_native_aibom, export_cyclonedx_aibom
from app.reporting.builder import build_due_diligence_report

router = APIRouter(prefix="/api/v1")

@router.post("/ingestion/otel")
def ingest_otel_trace(company_id: str, payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    """Ingests OpenTelemetry trace payload adhering to GenAI semantic conventions."""
    try:
        trace = process_otlp_payload(db, company_id, payload)
        return {
            "status": "success",
            "trace_id": trace.id,
            "spans_count": len(trace.spans),
            "total_cost_usd": trace.total_cost,
            "provenance_hash": trace.provenance_hash
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/scenarios/{scenario_name}/run")
def run_benchmark_scenario(scenario_name: str = "scenario_a", sample_size: int = 500, db: Session = Depends(get_db)):
    """Runs benchmark scenario and generates standardized diligence package immediately."""
    try:
        synth_res = generate_synthetic_scenario(db, scenario_name=scenario_name.lower(), sample_size=sample_size, seed=42)
        company_id = synth_res["company_id"]
        package = build_due_diligence_report(db, company_id)
        return package
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/companies/{company_id}/package")
def get_diligence_package(company_id: str, db: Session = Depends(get_db)):
    """Returns standardized diligence package for a company."""
    try:
        report = db.query(Report).filter(Report.company_id == company_id).order_by(Report.created_at.desc()).first()
        if report and report.summary_json:
            return report.summary_json
        return build_due_diligence_report(db, company_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/companies/{company_id}/aibom/cyclonedx")
def get_cyclonedx_aibom(
    company_id: str,
    spec_version: str = Query("1.6", pattern="^(1.5|1.6)$"),
    db: Session = Depends(get_db)
):
    """Exports CycloneDX 1.6 or 1.5-compatible AIBOM JSON with schema validation status."""
    try:
        from app.aibom.generator import validate_cyclonedx_schema
        native_bom = generate_native_aibom(db, company_id)
        cdx = export_cyclonedx_aibom(native_bom, spec_version=spec_version)
        is_valid, errors = validate_cyclonedx_schema(cdx, spec_version=spec_version)
        headers = {
            "X-CycloneDX-SpecVersion": spec_version,
            "X-CycloneDX-Valid": "true" if is_valid else "false"
        }
        if not is_valid:
            headers["X-CycloneDX-Validation-Error"] = "; ".join(errors)
            return JSONResponse(
                status_code=422,
                content={
                    "detail": f"CycloneDX schema validation failed: {'; '.join(errors)}",
                    "errors": errors,
                    "bom": cdx
                },
                headers=headers
            )
        return JSONResponse(content=cdx, headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/companies/{company_id}/manifest")
def get_chain_of_custody_manifest(company_id: str, db: Session = Depends(get_db)):
    """Returns the cryptographic chain-of-custody manifest."""
    try:
        report = db.query(Report).filter(Report.company_id == company_id).order_by(Report.created_at.desc()).first()
        if report and report.summary_json and "audit_manifest" in report.summary_json:
            return report.summary_json["audit_manifest"]
        package = build_due_diligence_report(db, company_id)
        return package.get("audit_manifest", {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/companies/{company_id}/pdf")
def get_diligence_pdf(company_id: str, db: Session = Depends(get_db)):
    """Downloads or previews the compiled PDF due diligence report."""
    report = db.query(Report).filter(Report.company_id == company_id).order_by(Report.created_at.desc()).first()
    if report and report.pdf_path and os.path.exists(str(report.pdf_path)):
        return FileResponse(str(report.pdf_path), media_type="application/pdf", filename=os.path.basename(str(report.pdf_path)))
    package = build_due_diligence_report(db, company_id)
    pdf_path = package.get("pdf_path")
    if pdf_path and os.path.exists(pdf_path):
        return FileResponse(pdf_path, media_type="application/pdf", filename=os.path.basename(pdf_path))
    raise HTTPException(status_code=404, detail="PDF report not found")

@router.post("/telemetry/upload")
def upload_telemetry(payload_wrapper: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    """
    Experimental endpoint to upload custom telemetry traces (OTel or Native format),
    instantiate a company audit, run analysis engines, and return the standardized package.
    """
    try:
        company_name = payload_wrapper.get("company_name", "Uploaded AI Target")
        data = payload_wrapper.get("payload", {})
        
        tenant = Tenant(name=f"Tenant for {company_name}")
        db.add(tenant)
        db.flush()
        
        company = Company(
            tenant_id=tenant.id,
            name=company_name,
            domain="custom-target.internal"
        )
        db.add(company)
        db.flush()
        
        # Add baseline pitch deck claims for verification
        claim1 = Claim(
            company_id=company.id,
            category="autonomy",
            claim_text="90.0% Autonomous Agent Operations",
            source="Due Diligence Questionnaire",
            target_value="90.0%"
        )
        claim2 = Claim(
            company_id=company.id,
            category="economics",
            claim_text="Telemetry-attributable cost under $0.0020 per task",
            source="Pitch Deck",
            target_value="$0.0020"
        )
        claim3 = Claim(
            company_id=company.id,
            category="dependency",
            claim_text="Resilient multi-model orchestration with low vendor lock-in",
            source="Architecture Whitepaper",
            target_value="Multi-Cloud"
        )
        db.add_all([claim1, claim2, claim3])
        db.flush()
        
        # Determine if payload is single trace or multiple traces
        traces_to_process = []
        if isinstance(data, list):
            traces_to_process = data
        elif isinstance(data, dict):
            if "traces" in data and isinstance(data["traces"], list):
                traces_to_process = data["traces"]
            elif "spans" in data:
                traces_to_process = [data]
            else:
                # Mock a trace if bare list of spans
                traces_to_process = [{"trace_id": str(uuid.uuid4()), "spans": data.get("spans", [])}]
                
        for t_data in traces_to_process:
            if not t_data.get("trace_id") and not t_data.get("traceId"):
                t_data["trace_id"] = str(uuid.uuid4())
            process_otlp_payload(db, company.id, t_data)
            
        db.commit()
        
        # Build Standardized Diligence Package
        package = build_due_diligence_report(db, company.id)
        return package
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to process custom telemetry: {str(e)}")

@router.get("/companies/{company_id}/autonomy")
def get_company_autonomy(company_id: str, db: Session = Depends(get_db)):
    """Returns deterministic Human Intervention Rate and autonomy breakdown."""
    return analyze_human_intervention(db, company_id)

@router.get("/companies/{company_id}/economics")
def get_company_economics(company_id: str, db: Session = Depends(get_db)):
    """Returns unit economics, cost per task, and latency percentiles."""
    return analyze_unit_economics(db, company_id)

@router.get("/companies/{company_id}/dependencies")
def get_company_dependencies(company_id: str, db: Session = Depends(get_db)):
    """Returns provider concentration and Herfindahl-Hirschman Index (HHI)."""
    return analyze_provider_dependencies(db, company_id)

@router.get("/companies/{company_id}/cascades")
def get_company_cascades(company_id: str, db: Session = Depends(get_db)):
    """Returns failure cascade and retry cost amplification metrics."""
    return analyze_failure_cascades(db, company_id)

@router.get("/companies/{company_id}/aibom")
def get_company_aibom(company_id: str, db: Session = Depends(get_db)):
    """Returns native AIBOM for a company."""
    return generate_native_aibom(db, company_id)

@router.get("/companies/{company_id}/tool-risk")
def get_company_tool_risk(company_id: str, db: Session = Depends(get_db)):
    """Returns tool privilege and sandbox execution risk assessment."""
    return analyze_tool_execution_risk(db, company_id)

@router.get("/companies/{company_id}/defensibility")
def get_company_defensibility(company_id: str, db: Session = Depends(get_db)):
    """Returns defensibility score, proprietary scaffolding, and moat analysis."""
    try:
        return analyze_defensibility_and_moat(db, company_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/companies/{company_id}/stress-test")
def run_company_stress_test(
    company_id: str,
    payload: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db)
):
    """
    Runs sensitivity and operational stress testing against token inflation,
    provider price shocks, volume scaling, and fully-loaded human labor economics.
    """
    try:
        vol = float(payload.get("volume_multiplier", 1.0))
        shock = float(payload.get("provider_price_shock_pct", 0.0))
        wage = float(payload.get("human_hourly_wage_usd", 28.0))
        price = float(payload.get("target_customer_price_per_task_usd", 0.05))
        tasks = int(payload.get("baseline_monthly_tasks", 50000))
        return simulate_stress_test_economics(
            db, company_id,
            volume_multiplier=vol,
            provider_price_shock_pct=shock,
            human_hourly_wage_usd=wage,
            target_customer_price_per_task_usd=price,
            baseline_monthly_tasks=tasks
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/companies/{company_id}/memo")
def get_company_memo(company_id: str, db: Session = Depends(get_db)):
    """Returns Investment Committee Executive Diligence Memo, Red Flags, and Deal Verdict."""
    try:
        return generate_investment_committee_memo(db, company_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/companies/{company_id}/bundle")
def download_diligence_bundle(company_id: str, db: Session = Depends(get_db)):
    """Downloads the complete cryptographically verifiable .zip diligence bundle."""
    package = build_due_diligence_report(db, company_id)
    pkg_files = package.get("package_files", {})
    bundle_path = pkg_files.get("diligence_bundle_zip")
    
    if bundle_path and os.path.exists(bundle_path):
        return FileResponse(
            bundle_path,
            media_type="application/zip",
            filename=os.path.basename(bundle_path)
        )
    raise HTTPException(status_code=404, detail="Diligence package bundle not found.")

@router.post("/packages/verify")
def verify_bundle_endpoint(payload: Dict[str, Any] = Body(...)):
    """
    Verifies the integrity, authenticity, and SHA-256 chain-of-custody seal
    of a diligence bundle given its file path.
    """
    bundle_path = payload.get("bundle_path")
    if not bundle_path:
        raise HTTPException(status_code=400, detail="Missing required 'bundle_path' parameter.")
    res = verify_diligence_bundle(bundle_path)
    return res

@router.get("/comparison")
def compare_companies_endpoint(
    company_a_id: str,
    company_b_id: str,
    db: Session = Depends(get_db)
):
    """Generates side-by-side comparative technical diligence matrix between two targets."""
    try:
        return compare_diligence_targets(db, company_a_id, company_b_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/comparison/scenarios")
def compare_scenarios_endpoint(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Runs two synthetic benchmark scenarios and compares them side-by-side.
    E.g. payload: {"scenario_a": "scenario_a", "scenario_b": "scenario_c", "sample_size": 300}
    """
    try:
        sc_a = payload.get("scenario_a", "scenario_a").lower()
        sc_b = payload.get("scenario_b", "scenario_c").lower()
        sample_size = payload.get("sample_size", 300)
        
        target_a_res = generate_synthetic_scenario(db, scenario_name=sc_a, sample_size=sample_size, seed=42)
        target_b_res = generate_synthetic_scenario(db, scenario_name=sc_b, sample_size=sample_size, seed=99)
        
        return compare_diligence_targets(db, target_a_res["company_id"], target_b_res["company_id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Phase 3: Task Segmentation & Deterministic Metrics Engine
# ---------------------------------------------------------------------------

@router.post("/traces/segment")
def segment_trace_endpoint(
    payload: Dict[str, Any] = Body(...),
):
    """
    Segments a list of normalized spans from a single trace into discrete tasks,
    classifying each as AUTONOMOUS / HUMAN_EXPLICIT / HUMAN_INFERRED / UNKNOWN.
    Returns epistemically-tagged autonomy bounds.

    Request body:
    {
        "trace_id": "abc123",
        "workflow_name": "my_agent_workflow",
        "gap_heuristic_ms": 30000,          # optional, default 30s
        "spans": [ ... NormalizedSpan dicts ... ]
    }
    """
    from app.analysis.task_segmentation import segment_trace
    from app.ingestion.normalizer import normalize_span_payload

    try:
        trace_id = payload.get("trace_id", "unspecified_trace")
        workflow_name = payload.get("workflow_name", "unknown_workflow")
        gap_ms = float(payload.get("gap_heuristic_ms", 30_000))
        raw_spans = payload.get("spans", [])

        normalized = [normalize_span_payload(s) for s in raw_spans]
        result = segment_trace(normalized, trace_id=trace_id,
                               workflow_name=workflow_name, gap_heuristic_ms=gap_ms)
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/traces/metrics")
def compute_metrics_endpoint(
    payload: Dict[str, Any] = Body(...),
):
    """
    Computes all 8 epistemically-tagged diligence signals from a list of
    pre-segmented traces and their spans.

    Request body:
    {
        "traces": [ ...TraceSegmentationResult.to_dict() outputs... ],
        "spans":  [ ...NormalizedSpan dicts... ]
    }
    """
    from app.analysis.task_segmentation import (
        segment_trace, SegmentedTask, TraceSegmentationResult,
        TaskOutcome, InterventionKind
    )
    from app.analysis.metrics_engine import compute_diligence_metrics
    from app.ingestion.normalizer import normalize_span_payload
    from app.epistemic.tags import TrustLevel, EpistemicTag

    try:
        raw_spans = payload.get("spans", [])
        normalized_spans = [normalize_span_payload(s) for s in raw_spans]

        # If segmentation results are provided, use them directly
        # Otherwise, group spans by trace_id and segment each
        all_results = []
        spans_by_trace: Dict[str, list] = {}
        for s in normalized_spans:
            spans_by_trace.setdefault(s.trace_id, []).append(s)

        for tid, t_spans in spans_by_trace.items():
            r = segment_trace(t_spans, trace_id=tid)
            all_results.append(r)

        metrics = compute_diligence_metrics(all_results, normalized_spans)
        return metrics.to_dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/companies/{company_id}/metrics")
def get_company_metrics(
    company_id: str,
    gap_heuristic_ms: float = 30_000,
    db: Session = Depends(get_db),
):
    """
    Computes Phase 3 task-segmented diligence metrics for a company
    whose traces are already stored in the database.

    Returns all 8 epistemically-tagged diligence signals.
    """
    from app.analysis.task_segmentation import segment_trace
    from app.analysis.metrics_engine import compute_diligence_metrics
    from app.ingestion.schema import NormalizedSpan as SchemaSpan
    from app.ingestion.normalizer import normalize_span_payload
    from app.epistemic.tags import TrustLevel
    from app.db.models import Trace, Span
    from datetime import datetime

    try:
        traces = db.query(Trace).filter(Trace.company_id == company_id).all()
        if not traces:
            raise HTTPException(status_code=404, detail=f"No traces found for company {company_id}")

        all_seg_results = []
        all_norm_spans = []

        for trace in traces:
            # Convert DB Span rows → NormalizedSpan
            norm_spans = []
            for sp in trace.spans:
                ns = SchemaSpan(
                    span_id=sp.id,
                    trace_id=trace.id,
                    name=sp.name,
                    span_kind=sp.span_kind,
                    start_time=sp.start_time,
                    end_time=sp.end_time,
                    duration_ms=sp.duration_ms,
                    # Derive status_code from actual DB error flag (was incorrectly hardcoded to "OK")
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
                    trust_level=TrustLevel.T1,
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
        return {
            "company_id": company_id,
            "traces_analyzed": len(traces),
            "gap_heuristic_ms": gap_heuristic_ms,
            **metrics.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies/{company_id}/claim-matrix")
def get_company_claim_matrix(company_id: str, db: Session = Depends(get_db)):
    """
    Returns the formal Phase 4 Claim Verification Matrix adhering to docs/phase-4/data-contracts.md.
    """
    try:
        from app.reporting.service import assemble_canonical_diligence_report_package
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
        _, _, matrix = assemble_canonical_diligence_report_package(db, company_id)
        return matrix.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/companies/{company_id}/diligence-report")
def get_company_diligence_report(
    company_id: str,
    format: str = Query("json", pattern="^(json|markdown)$"),
    is_synthetic: bool = Query(False),
    db: Session = Depends(get_db)
):
    """
    Returns the Phase 4 Canonical Diligence Report in JSON or Markdown format.
    """
    try:
        from app.reporting.service import assemble_canonical_diligence_report_package
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
        rep_json, rep_md, _ = assemble_canonical_diligence_report_package(db, company_id, is_synthetic=is_synthetic)
        if format == "markdown":
            return PlainTextResponse(content=rep_md, media_type="text/markdown")
        return rep_json
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/companies/{company_id}/bundle")
def create_company_bundle(
    company_id: str,
    payload: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db)
):
    """
    Compiles an evidence bundle and cryptographic manifest on disk.
    """
    try:
        from app.reporting.service import compile_diligence_bundle_on_disk
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
        out_dir = payload.get("output_dir")
        if out_dir:
            norm_out = os.path.normpath(out_dir)
            if ".." in norm_out.split(os.sep):
                raise HTTPException(status_code=400, detail="Path traversal forbidden in output_dir")
        else:
            out_dir = os.path.join(".", "bundles", company_id)

        is_synth = payload.get("is_synthetic", False)
        bundle_info = compile_diligence_bundle_on_disk(db, company_id, out_dir, is_synthetic=is_synth)
        return bundle_info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bundles/verify")
def verify_bundle_endpoint(payload: Dict[str, Any] = Body(...)):
    """
    Verifies the cryptographic integrity and completeness of an evidence bundle directory.
    """
    try:
        from app.reporting.manifest import verify_bundle_integrity
        bundle_dir = payload.get("bundle_dir")
        if not bundle_dir or not isinstance(bundle_dir, str):
            raise HTTPException(status_code=400, detail="bundle_dir must be a valid directory path string")
        norm_dir = os.path.normpath(bundle_dir)
        if ".." in norm_dir.split(os.sep):
            raise HTTPException(status_code=400, detail="Path traversal forbidden in bundle_dir")
        if not os.path.exists(norm_dir) or not os.path.isdir(norm_dir):
            raise HTTPException(status_code=400, detail=f"Bundle directory '{bundle_dir}' not found or is not a directory")
        result = verify_bundle_integrity(norm_dir)
        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# Phase 6: Unified Evidence Ingestion & Verification Endpoints
# ==============================================================================

@router.post("/evidence/ingest")
def ingest_unified_evidence(
    payload: Dict[str, Any] = Body(...),
    source_type: Optional[str] = Query(None, description="Optional adapter hint: 'otlp', 'mcp', or 'browser'"),
    company_id: Optional[str] = Query("default_target", description="Target company identifier"),
    content_type: str = Query("application/json"),
    db: Session = Depends(get_db)
):
    """
    Ingests telemetry evidence from OTLP, MCP, or Browser sources into the Unified Evidence Registry.
    Computes cryptographic SHA-256 provenance digests and handles idempotency.
    """
    from app.adapters.pipeline import default_pipeline
    import json
    try:
        raw_bytes = json.dumps(payload).encode("utf-8")
        receipt = default_pipeline.ingest_evidence(
            raw_bytes=raw_bytes,
            source_type=source_type,
            company_id=company_id,
            content_type=content_type,
            db=db,
        )
        return receipt.to_dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/evidence/verify")
def verify_unified_claims(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Executes claim verification over multi-source correlated telemetry in the unified registry.
    Returns explainable verdicts (VERIFIED, CONTRADICTED, INSUFFICIENT_EVIDENCE).
    """
    from app.adapters.pipeline import default_pipeline
    from app.epistemic.claims import ClaimSchema, ClaimDimension, ComparisonOperator
    from app.epistemic.tags import TrustLevel
    try:
        company_id = payload.get("company_id", "default_target")
        raw_claims = payload.get("claims", [])
        min_sample_size = int(payload.get("min_sample_size", 15))

        claims: List[ClaimSchema] = []
        for rc in raw_claims:
            claims.append(ClaimSchema(
                claim_id=rc.get("claim_id", f"claim-{len(claims)+1}"),
                dimension=ClaimDimension(rc.get("dimension", "autonomy")),
                stated_claim_text=rc.get("stated_claim_text", ""),
                target_operator=ComparisonOperator(rc.get("target_operator", ">=")),
                target_value=float(rc.get("target_value", 0.0)),
                unit=rc.get("unit", "%"),
                evidence_trust_minimum=TrustLevel(rc.get("evidence_trust_minimum", "T1")),
                source_document=rc.get("source_document", "Pitch Deck"),
                tolerance_pct=float(rc.get("tolerance_pct", 5.0)),
            ))

        result = default_pipeline.verify_claims(
            claims=claims,
            company_id=company_id,
            min_sample_size=min_sample_size,
            db=db,
        )
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/evidence/records")
def list_evidence_records(
    company_id: Optional[str] = Query(None),
    trace_id: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    include_duplicates: bool = Query(False),
):
    """Lists registered evidence records matching filters."""
    from app.adapters.pipeline import default_pipeline
    from app.adapters.registry import SourceType
    try:
        st = SourceType(source_type) if source_type else None
        records = default_pipeline.registry.get_records(
            company_id=company_id,
            trace_id=trace_id,
            source_type=st,
            include_duplicates=include_duplicates,
        )
        return [r.to_dict() for r in records]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/evidence/provenance")
def get_provenance_envelopes(
    company_id: Optional[str] = Query(None),
):
    """Returns cryptographic provenance envelopes registered for diligence scope."""
    from app.adapters.pipeline import default_pipeline
    try:
        envelopes = default_pipeline.registry.get_provenance_envelopes(company_id=company_id)
        return [e.to_dict() for e in envelopes]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

