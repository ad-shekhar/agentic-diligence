import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.db.models import Company, Report, Claim, Trace
from app.analysis.intervention import analyze_human_intervention
from app.analysis.economics import analyze_unit_economics
from app.analysis.evaluation import analyze_evaluation_overhead
from app.analysis.dependency import analyze_provider_dependencies
from app.analysis.cascade import analyze_failure_cascades
from app.analysis.tool_risk import analyze_tool_execution_risk
from app.aibom.generator import generate_native_aibom, export_cyclonedx_aibom
from app.evidence.engine import generate_evidence_package
from app.reporting.pdf import generate_pdf_report
from app.reporting.manifest import build_chain_of_custody_manifest
from app.reporting.bundle import create_diligence_bundle

def build_due_diligence_report(
    db: Session,
    company_id: str,
    pdf_output_path: str = None,
    output_dir: str = None
) -> Dict[str, Any]:
    """
    Assembles a complete, standardized technical diligence package:
    - Pitch deck claim verification matrix
    - Native AIBOM and CycloneDX-compatible export
    - Cascade failure & economic overrun analysis
    - Multi-dimensional Potential SPOF analysis
    - Auditable Evidence Graph
    - Cryptographic Chain-of-Custody Manifest
    - PDF Report
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise ValueError(f"Company {company_id} not found")
        
    if not output_dir:
        output_dir = "."
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Deterministic Analytical Engines
    intervention = analyze_human_intervention(db, company_id)
    economics = analyze_unit_economics(db, company_id)
    evaluation = analyze_evaluation_overhead(db, company_id)
    dependency = analyze_provider_dependencies(db, company_id)
    cascades = analyze_failure_cascades(db, company_id)
    tool_risk = analyze_tool_execution_risk(db, company_id)
    
    # 2. Native AIBOM & CycloneDX Export
    native_aibom_obj = generate_native_aibom(db, company_id)
    native_aibom_dict = native_aibom_obj.model_dump() if hasattr(native_aibom_obj, "model_dump") else native_aibom_obj.dict()
    cyclonedx_aibom_dict = export_cyclonedx_aibom(native_aibom_obj)
    
    # 3. Evidence Engine & Claim Verifications
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
        
    company_slug = company.name.lower().replace(' ', '_').replace('(', '').replace(')', '')
    if not pdf_output_path:
        pdf_output_path = os.path.join(output_dir, f"diligence_report_{company_slug}.pdf")
        
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
        "cascades": cascades,
        "tool_risk": tool_risk,
        "aibom": native_aibom_dict,
        "limitations": dynamic_limitations,
        "evidence_records": evd_json,
        "report_metadata": {
            "platform": "Agentic Diligence",
            "version": "1.0.0-standardized",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pricing_version": "v2026_09"
        }
    }
    
    # 4. Generate PDF Report
    pdf_path = generate_pdf_report(report_data, pdf_output_path)
    
    # 5. Build Cryptographic Chain-of-Custody Manifest
    trace_hashes = [
        t.provenance_hash for t in db.query(Trace.provenance_hash).filter(Trace.company_id == company_id).all()
        if t.provenance_hash
    ]
    report_json_str = json.dumps(report_data, indent=2, default=str)
    aibom_native_str = json.dumps(native_aibom_dict, indent=2, default=str)
    aibom_cyclonedx_str = json.dumps(cyclonedx_aibom_dict, indent=2, default=str)
    
    manifest = build_chain_of_custody_manifest(
        company_id=company.id,
        company_name=company.name,
        trace_hashes=trace_hashes,
        evidence_records=evd_json,
        report_json_str=report_json_str,
        pdf_path=pdf_path,
        aibom_native_str=aibom_native_str,
        aibom_cyclonedx_str=aibom_cyclonedx_str
    )
    
    report_data["audit_manifest"] = manifest
    report_data["pdf_path"] = pdf_path
    
    # 6. Save Package Files to Output Directory
    package_json_path = os.path.join(output_dir, f"diligence_package_{company_slug}.json")
    with open(package_json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, default=str)
        
    manifest_path = os.path.join(output_dir, f"audit_manifest_{company_slug}.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)
        
    aibom_native_path = os.path.join(output_dir, f"aibom_native_{company_slug}.json")
    with open(aibom_native_path, "w", encoding="utf-8") as f:
        json.dump(native_aibom_dict, f, indent=2, default=str)
        
    aibom_cyclonedx_path = os.path.join(output_dir, f"aibom_cyclonedx_{company_slug}.json")
    with open(aibom_cyclonedx_path, "w", encoding="utf-8") as f:
        json.dump(cyclonedx_aibom_dict, f, indent=2, default=str)
        
    bundle_zip_path = os.path.join(output_dir, f"diligence_package_{company_slug}.zip")
    
    report_data["package_files"] = {
        "pdf_report": os.path.abspath(pdf_path),
        "package_json": os.path.abspath(package_json_path),
        "audit_manifest": os.path.abspath(manifest_path),
        "aibom_native": os.path.abspath(aibom_native_path),
        "aibom_cyclonedx": os.path.abspath(aibom_cyclonedx_path),
        "diligence_bundle_zip": os.path.abspath(bundle_zip_path)
    }
    
    # Re-generate PDF with audit manifest included
    generate_pdf_report(report_data, pdf_output_path)
    
    # Package into verifiable .zip bundle
    create_diligence_bundle(report_data, bundle_zip_path)
    
    # 8. Save Report record in DB
    db_report = Report(
        company_id=company_id,
        title=f"Technical Due Diligence Report - {company.name}",
        summary_json=report_data,
        pdf_path=pdf_path
    )
    db.add(db_report)
    db.commit()
    
    report_data["report_id"] = db_report.id
    return report_data
