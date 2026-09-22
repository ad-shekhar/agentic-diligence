import os
import json
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.db.models import Company, Report, Claim
from app.analysis.intervention import analyze_human_intervention
from app.analysis.economics import analyze_unit_economics
from app.analysis.evaluation import analyze_evaluation_overhead
from app.analysis.dependency import analyze_provider_dependencies
from app.evidence.engine import generate_evidence_package
from app.reporting.pdf import generate_pdf_report

def build_due_diligence_report(db: Session, company_id: str, pdf_output_path: str = None) -> Dict[str, Any]:
    """
    Assembles complete evidence-backed due diligence report, saves to DB and renders PDF.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise ValueError(f"Company {company_id} not found")
        
    intervention = analyze_human_intervention(db, company_id)
    economics = analyze_unit_economics(db, company_id)
    evaluation = analyze_evaluation_overhead(db, company_id)
    dependency = analyze_provider_dependencies(db, company_id)
    
    evidence_records = generate_evidence_package(
        db, company_id, intervention, economics, evaluation, dependency
    )
    
    db_claims = db.query(Claim).filter(Claim.company_id == company_id).all()
    claims_list = [
        {
            "id": c.id,
            "category": c.category,
            "claim_text": c.claim_text,
            "source": c.source,
            "target_value": c.target_value,
            "observed_value": c.observed_value,
            "verification_status": c.verification_status.value if hasattr(c.verification_status, "value") else str(c.verification_status),
            "verification_reason": c.verification_reason,
            "confidence": c.confidence.value if hasattr(c.confidence, "value") else str(c.confidence)
        }
        for c in db_claims
    ]
    
    evd_json = [
        {
            "evidence_code": e.evidence_code,
            "evidence_type": e.evidence_type.value if hasattr(e.evidence_type, "value") else str(e.evidence_type),
            "confidence": e.confidence.value if hasattr(e.confidence, "value") else str(e.confidence),
            "verification_status": e.verification_status.value if (e.verification_status and hasattr(e.verification_status, "value")) else str(e.verification_status),
            "claim_summary": e.claim_summary,
            "observed_fact": e.observed_fact,
            "derived_metric_summary": e.derived_metric_summary,
            "inference_summary": e.inference_summary,
            "data_source_description": e.data_source_description,
            "sample_size": e.sample_size,
            "verification_method": e.verification_method,
            "observation_window": e.observation_window,
            "pricing_version": e.pricing_version,
            "limitations": e.limitations
        }
        for e in evidence_records
    ]
    
    # Dynamic Limitations
    dynamic_limitations = [
        "Only instrumented agent workflows in available telemetry were analyzed.",
        "Human intervention occurring outside instrumented software systems cannot be detected.",
        "Telemetry-attributable cost excludes infrastructure hosting, human operational labor, and legal governance overhead.",
        "Provider pricing calculations reference static versioned rates (v2026_09) and may differ from custom enterprise contracts."
    ]
    if evaluation["insufficient_coverage_flag"]:
        dynamic_limitations.append("Low evaluation coverage (<20%) limits confidence in automated quality control effectiveness.")
    if economics["overall_cost_status"] == "UNKNOWN":
        dynamic_limitations.append("Telemetry contains unpriced custom models; total cost is partially unestablished.")
        
    report_data = {
        "company": {
            "id": company.id,
            "name": company.name,
            "domain": company.domain
        },
        "observation_window": "Last 30 Days",
        "data_coverage": intervention["data_coverage"],
        "claims": claims_list,
        "interventions": intervention,
        "economics": economics,
        "evaluation": evaluation,
        "dependencies": dependency,
        "limitations": dynamic_limitations,
        "evidence_records": evd_json,
        "report_metadata": {
            "platform": "Agentic Diligence",
            "version": "0.1.0-hardened",
            "generated_at": datetime.utcnow().isoformat(),
            "pricing_version": "v2026_09"
        }
    }
    
    if not pdf_output_path:
        pdf_output_path = f"diligence_report_{company.name.lower().replace(' ', '_').replace('(', '').replace(')', '')}.pdf"
        
    pdf_path = generate_pdf_report(report_data, pdf_output_path)
    
    # Save Report record in DB
    db_report = Report(
        company_id=company_id,
        title=f"Technical Due Diligence Report - {company.name}",
        summary_json=report_data,
        pdf_path=pdf_path
    )
    db.add(db_report)
    db.commit()
    
    report_data["report_id"] = db_report.id
    report_data["pdf_path"] = pdf_path
    
    return report_data
