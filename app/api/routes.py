from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.db.session import get_db
from app.ingestion.otel import process_otlp_payload
from app.ingestion.synthetic import generate_synthetic_scenario
from app.analysis.intervention import analyze_human_intervention
from app.analysis.economics import analyze_unit_economics
from app.analysis.dependency import analyze_provider_dependencies
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
            "total_cost_usd": trace.total_cost
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/scenarios/generate")
def generate_benchmark_scenario(scenario_name: str = "scenario_a", sample_size: int = 500, db: Session = Depends(get_db)):
    """Generates synthetic telemetry for a benchmark scenario."""
    try:
        res = generate_synthetic_scenario(db, scenario_name=scenario_name, sample_size=sample_size)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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

@router.post("/reports/generate")
def generate_report(company_id: str, pdf_filename: str = "diligence_report.pdf", db: Session = Depends(get_db)):
    """Generates complete evidence-backed due diligence report and PDF artifact."""
    try:
        return build_due_diligence_report(db, company_id, pdf_filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
