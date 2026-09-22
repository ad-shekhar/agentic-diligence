from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.db.models import Claim, EvidenceRecord, EvidenceType, ConfidenceLevel, VerificationStatus
from app.evidence.verifier import verify_autonomy_claim, verify_economics_claim, verify_dependency_claim

def generate_evidence_package(
    db: Session,
    company_id: str,
    intervention_results: Dict[str, Any],
    economics_results: Dict[str, Any],
    evaluation_results: Dict[str, Any],
    dependency_results: Dict[str, Any]
) -> List[EvidenceRecord]:
    """
    Synthesizes structured evidence records mapping claims to observed telemetry facts.
    """
    claims = db.query(Claim).filter(Claim.company_id == company_id).all()
    evidence_list = []
    
    # 1. Autonomy Claim Verification & Evidence Graph Node
    auto_claim = next((c for c in claims if c.category == "autonomy"), None)
    obs_auto = intervention_results["autonomous_rate_pct"]
    sample_size = intervention_results["total_traces"]
    
    v_status_auto, v_reason_auto, conf_auto = verify_autonomy_claim(
        auto_claim.claim_text if auto_claim else "95.0% Autonomous",
        95.0, obs_auto, sample_size
    )
    
    if auto_claim:
        auto_claim.observed_value = f"{obs_auto:.1f}%"
        auto_claim.verification_status = v_status_auto
        auto_claim.verification_reason = v_reason_auto
        auto_claim.confidence = conf_auto
        
    evd_auto = EvidenceRecord(
        claim_id=auto_claim.id if auto_claim else None,
        evidence_code="EVD-001",
        evidence_type=EvidenceType.DERIVED_METRIC,
        confidence=conf_auto,
        verification_status=v_status_auto,
        claim_summary=auto_claim.claim_text if auto_claim else "Claimed 95.0% Autonomous",
        observed_fact=f"{intervention_results['autonomous_traces']} of {sample_size} available traces completed without human intervention.",
        derived_metric_summary=f"Autonomous workflow completion rate = {obs_auto:.1f}%. Human Intervention Rate (HIR) = {intervention_results['human_intervention_rate_pct']:.1f}%.",
        inference_summary=v_reason_auto,
        data_source_description="OpenTelemetry GenAI span attributes & latency gap analysis",
        sample_size=sample_size,
        verification_method="Deterministic span classification & latency gap heuristics (>300s)",
        observation_window="Last 30 Days",
        pricing_version="v2026_09",
        limitations="Intervention occurring outside instrumented systems cannot be detected."
    )
    db.add(evd_auto)
    evidence_list.append(evd_auto)
    
    # 2. Economics Claim Verification & Evidence Graph Node
    econ_claim = next((c for c in claims if c.category == "economics"), None)
    obs_cost = economics_results["telemetry_attributable_cost_per_task_usd"]
    
    v_status_econ, v_reason_econ, conf_econ = verify_economics_claim(
        econ_claim.claim_text if econ_claim else "$0.0010 per task",
        0.0010, obs_cost, sample_size
    )
    
    if econ_claim:
        econ_claim.observed_value = f"${obs_cost:.4f}"
        econ_claim.verification_status = v_status_econ
        econ_claim.verification_reason = v_reason_econ
        econ_claim.confidence = conf_econ
        
    evd_econ = EvidenceRecord(
        claim_id=econ_claim.id if econ_claim else None,
        evidence_code="EVD-002",
        evidence_type=EvidenceType.DERIVED_METRIC,
        confidence=conf_econ,
        verification_status=v_status_econ,
        claim_summary=econ_claim.claim_text if econ_claim else "Claimed $0.0010 per task",
        observed_fact=f"Total measured telemetry cost of ${economics_results['total_measured_cost_usd']:.2f} across {sample_size} tasks.",
        derived_metric_summary=f"Telemetry-attributable cost per task = ${obs_cost:.4f} (Status: {economics_results['overall_cost_status']}).",
        inference_summary=v_reason_econ,
        data_source_description="Versioned Model Pricing Table (v2026_09) applied to token counts in trace spans",
        sample_size=sample_size,
        verification_method="Span token count aggregation multiplied by official model pricing",
        observation_window="Last 30 Days",
        pricing_version="v2026_09",
        limitations="Excludes unmeasured infrastructure, human operations, and governance costs."
    )
    db.add(evd_econ)
    evidence_list.append(evd_econ)
    
    # 3. Provider Dependency Claim Verification & Evidence Graph Node
    dep_claim = next((c for c in claims if c.category == "dependency"), None)
    hhi = dependency_results["hhi_score"]
    primary_share = dependency_results["providers"][0]["share_pct"] if dependency_results["providers"] else 0.0
    
    v_status_dep, v_reason_dep, conf_dep = verify_dependency_claim(
        dep_claim.claim_text if dep_claim else "Multi-cloud resilient",
        hhi, primary_share
    )
    
    if dep_claim:
        dep_claim.observed_value = f"Primary Share: {primary_share:.1f}%, HHI: {hhi:.3f}"
        dep_claim.verification_status = v_status_dep
        dep_claim.verification_reason = v_reason_dep
        dep_claim.confidence = conf_dep
        
    evd_dep = EvidenceRecord(
        claim_id=dep_claim.id if dep_claim else None,
        evidence_code="EVD-003",
        evidence_type=EvidenceType.DERIVED_METRIC,
        confidence=conf_dep,
        verification_status=v_status_dep,
        claim_summary=dep_claim.claim_text if dep_claim else "Claimed multi-cloud resilience",
        observed_fact=f"Primary model provider ({dependency_results['providers'][0]['provider_name'] if dependency_results['providers'] else 'N/A'}) represents {primary_share:.1f}% of cost.",
        derived_metric_summary=f"Herfindahl-Hirschman Index (HHI) = {hhi:.3f} ({dependency_results['concentration_level']}).",
        inference_summary=v_reason_dep,
        data_source_description="Trace span provider attributes (gen_ai.system)",
        sample_size=sample_size,
        verification_method="HHI concentration formula applied to provider cost shares",
        observation_window="Last 30 Days",
        pricing_version="v2026_09",
        limitations="HHI calculation based on observed cost shares in available telemetry."
    )
    db.add(evd_dep)
    evidence_list.append(evd_dep)
    
    # 4. Trust Tax / Evaluation Overhead Evidence Node
    evd_eval = EvidenceRecord(
        claim_id=None,
        evidence_code="EVD-004",
        evidence_type=EvidenceType.DERIVED_METRIC,
        confidence=ConfidenceLevel.HIGH,
        verification_status=VerificationStatus.INSUFFICIENT_EVIDENCE if evaluation_results["insufficient_coverage_flag"] else VerificationStatus.VERIFIED,
        claim_summary="Automated Evaluation & Trust Tax Overhead",
        observed_fact=f"Evaluation spans present in {evaluation_results['eval_coverage_pct']}% of total workflow traces ({evaluation_results['eval_traces_count']}/{sample_size}).",
        derived_metric_summary=f"Trust Tax (Evaluation Overhead Rate) = {evaluation_results['trust_tax_rate_pct']}%. Status: {evaluation_results['evaluation_status']}.",
        inference_summary=evaluation_results["note"],
        data_source_description="Evaluation span telemetry classification (span_kind=evaluation)",
        sample_size=sample_size,
        verification_method="Ratio of evaluation span costs to primary inference span costs",
        observation_window="Last 30 Days",
        pricing_version="v2026_09",
        limitations="Low evaluation coverage may indicate unmonitored agent operations."
    )
    db.add(evd_eval)
    evidence_list.append(evd_eval)
    
    db.commit()
    return evidence_list
