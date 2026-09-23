import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, List

from app.db.session import get_db
from app.db.models import Company, Tenant, Claim, Report
from app.ingestion.otel import process_otlp_payload
from app.ingestion.synthetic import generate_synthetic_scenario
from app.analysis.intervention import analyze_human_intervention
from app.analysis.economics import analyze_unit_economics
from app.analysis.dependency import analyze_provider_dependencies
from app.analysis.cascade import analyze_failure_cascades
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
def get_cyclonedx_aibom(company_id: str, db: Session = Depends(get_db)):
    """Exports CycloneDX 1.6-compatible AIBOM JSON."""
    try:
        native_bom = generate_native_aibom(db, company_id)
        return export_cyclonedx_aibom(native_bom)
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
