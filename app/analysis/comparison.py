from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.db.models import Company, Report
from app.reporting.builder import build_due_diligence_report

def get_or_build_report(db: Session, company_id: str) -> Dict[str, Any]:
    """Retrieves the latest report for a company or builds one on-demand."""
    rep = db.query(Report).filter(Report.company_id == company_id).order_by(Report.created_at.desc()).first()
    if rep and rep.summary_json:
        return rep.summary_json
    return build_due_diligence_report(db, company_id)

def compare_diligence_targets(db: Session, company_a_id: str, company_b_id: str) -> Dict[str, Any]:
    """
    Computes a rigorous, side-by-side comparative technical diligence matrix
    between two AI agent targets across autonomy, economics, dependencies,
    failure cascades, evaluation overhead, and tool privilege risk.
    """
    pkg_a = get_or_build_report(db, company_a_id)
    pkg_b = get_or_build_report(db, company_b_id)
    
    comp_a_name = pkg_a.get("company", {}).get("name", "Target A")
    comp_b_name = pkg_b.get("company", {}).get("name", "Target B")
    
    # 1. Autonomy Comparison
    auto_a = pkg_a.get("interventions", {})
    auto_b = pkg_b.get("interventions", {})
    hir_a = auto_a.get("human_intervention_rate_pct", 0.0)
    hir_b = auto_b.get("human_intervention_rate_pct", 0.0)
    auto_rate_a = auto_a.get("autonomous_rate_pct", 100.0 - hir_a)
    auto_rate_b = auto_b.get("autonomous_rate_pct", 100.0 - hir_b)
    
    # 2. Economics Comparison
    econ_a = pkg_a.get("economics", {})
    econ_b = pkg_b.get("economics", {})
    cost_a = econ_a.get("telemetry_attributable_cost_per_task_usd", 0.0)
    cost_b = econ_b.get("telemetry_attributable_cost_per_task_usd", 0.0)
    p95_a = econ_a.get("p95_cost_usd", cost_a * 1.5)
    p95_b = econ_b.get("p95_cost_usd", cost_b * 1.5)
    
    # 3. Dependencies & Concentration
    dep_a = pkg_a.get("dependencies", {})
    dep_b = pkg_b.get("dependencies", {})
    hhi_a = dep_a.get("hhi_score", 0)
    hhi_b = dep_b.get("hhi_score", 0)
    top_prov_a = dep_a.get("top_provider_share_pct", 0.0)
    top_prov_b = dep_b.get("top_provider_share_pct", 0.0)
    
    # 4. Cascades & Resiliency
    casc_a = pkg_a.get("cascades", {})
    casc_b = pkg_b.get("cascades", {})
    casc_freq_a = casc_a.get("cascade_frequency_pct", 0.0)
    casc_freq_b = casc_b.get("cascade_frequency_pct", 0.0)
    overrun_mult_a = casc_a.get("avg_cost_multiplier_on_failure", 1.0)
    overrun_mult_b = casc_b.get("avg_cost_multiplier_on_failure", 1.0)
    
    # 5. Evaluation / Trust Tax
    eval_a = pkg_a.get("evaluation", {})
    eval_b = pkg_b.get("evaluation", {})
    tax_a = eval_a.get("trust_tax_rate_pct", 0.0)
    tax_b = eval_b.get("trust_tax_rate_pct", 0.0)
    cov_a = eval_a.get("eval_coverage_pct", 0.0)
    cov_b = eval_b.get("eval_coverage_pct", 0.0)
    
    # 6. Tool Risk
    tool_a = pkg_a.get("tool_risk", {})
    tool_b = pkg_b.get("tool_risk", {})
    tool_score_a = tool_a.get("tool_risk_score", 0.0)
    tool_score_b = tool_b.get("tool_risk_score", 0.0)
    
    # 7. Claim Veracity
    claims_a = pkg_a.get("claims", [])
    claims_b = pkg_b.get("claims", [])
    verified_a = sum(1 for c in claims_a if c.get("verification_status") == "VERIFIED")
    contra_a = sum(1 for c in claims_a if c.get("verification_status") == "CONTRADICTED")
    verified_b = sum(1 for c in claims_b if c.get("verification_status") == "VERIFIED")
    contra_b = sum(1 for c in claims_b if c.get("verification_status") == "CONTRADICTED")
    
    total_cl_a = len(claims_a) or 1
    total_cl_b = len(claims_b) or 1
    
    # Dimension Winners
    # Autonomy: higher autonomous rate wins
    autonomy_winner = comp_a_name if auto_rate_a > auto_rate_b else (comp_b_name if auto_rate_b > auto_rate_a else "TIE")
    # Unit Economics: lower cost per task wins
    economics_winner = comp_a_name if cost_a < cost_b else (comp_b_name if cost_b < cost_a else "TIE")
    # Architectural Resilience: lower HHI (more diversified) & lower cascade freq wins
    resilience_score_a = (hhi_a / 100.0) + casc_freq_a
    resilience_score_b = (hhi_b / 100.0) + casc_freq_b
    resilience_winner = comp_a_name if resilience_score_a < resilience_score_b else (comp_b_name if resilience_score_b < resilience_score_a else "TIE")
    # Governance & Verification: more verified claims and lower tool risk wins
    gov_winner = comp_a_name if (verified_a / total_cl_a) > (verified_b / total_cl_b) else (comp_b_name if (verified_b / total_cl_b) > (verified_a / total_cl_a) else "TIE")
    
    comparison_matrix = [
        {
            "dimension": "True Autonomy Rate",
            "metric": "Autonomous Completion Rate",
            "unit": "%",
            "target_a_value": f"{auto_rate_a:.1f}%",
            "target_b_value": f"{auto_rate_b:.1f}%",
            "delta": f"{auto_rate_a - auto_rate_b:+.1f}%",
            "advantage": comp_a_name if auto_rate_a > auto_rate_b else comp_b_name
        },
        {
            "dimension": "Human Intervention",
            "metric": "Human Intervention Rate (HIR)",
            "unit": "%",
            "target_a_value": f"{hir_a:.1f}%",
            "target_b_value": f"{hir_b:.1f}%",
            "delta": f"{hir_a - hir_b:+.1f}%",
            "advantage": comp_a_name if hir_a < hir_b else comp_b_name
        },
        {
            "dimension": "Unit Economics",
            "metric": "Telemetry Cost Per Task",
            "unit": "$",
            "target_a_value": f"${cost_a:.4f}",
            "target_b_value": f"${cost_b:.4f}",
            "delta": f"${cost_a - cost_b:+.4f}",
            "advantage": comp_a_name if cost_a < cost_b else comp_b_name
        },
        {
            "dimension": "Tail Cost Risk",
            "metric": "p95 Cost Per Task",
            "unit": "$",
            "target_a_value": f"${p95_a:.4f}",
            "target_b_value": f"${p95_b:.4f}",
            "delta": f"${p95_a - p95_b:+.4f}",
            "advantage": comp_a_name if p95_a < p95_b else comp_b_name
        },
        {
            "dimension": "Vendor Concentration",
            "metric": "Provider HHI Index",
            "unit": "HHI (0.0-1.0)",
            "target_a_value": f"{float(hhi_a):.4f}",
            "target_b_value": f"{float(hhi_b):.4f}",
            "delta": f"{float(hhi_a) - float(hhi_b):+.4f}",
            "advantage": comp_a_name if hhi_a < hhi_b else comp_b_name
        },
        {
            "dimension": "Failure Cascade Risk",
            "metric": "Cascade Frequency",
            "unit": "%",
            "target_a_value": f"{casc_freq_a:.1f}%",
            "target_b_value": f"{casc_freq_b:.1f}%",
            "delta": f"{casc_freq_a - casc_freq_b:+.1f}%",
            "advantage": comp_a_name if casc_freq_a < casc_freq_b else comp_b_name
        },
        {
            "dimension": "Overrun Penalty",
            "metric": "Cascade Cost Multiplier",
            "unit": "x",
            "target_a_value": f"{overrun_mult_a:.2f}x",
            "target_b_value": f"{overrun_mult_b:.2f}x",
            "delta": f"{overrun_mult_a - overrun_mult_b:+.2f}x",
            "advantage": comp_a_name if overrun_mult_a < overrun_mult_b else comp_b_name
        },
        {
            "dimension": "Evaluation Coverage",
            "metric": "Automated Eval Coverage",
            "unit": "%",
            "target_a_value": f"{cov_a:.1f}%",
            "target_b_value": f"{cov_b:.1f}%",
            "delta": f"{cov_a - cov_b:+.1f}%",
            "advantage": comp_a_name if cov_a > cov_b else comp_b_name
        },
        {
            "dimension": "Trust Tax",
            "metric": "Evaluation Overhead Rate",
            "unit": "%",
            "target_a_value": f"{tax_a:.1f}%",
            "target_b_value": f"{tax_b:.1f}%",
            "delta": f"{tax_a - tax_b:+.1f}%",
            "advantage": "N/A" # High eval can be positive for safety, negative for cost
        },
        {
            "dimension": "Tool Risk Score",
            "metric": "Privilege & Blast Radius Index",
            "unit": "Score (0-100)",
            "target_a_value": f"{tool_score_a:.1f}",
            "target_b_value": f"{tool_score_b:.1f}",
            "delta": f"{tool_score_a - tool_score_b:+.1f}",
            "advantage": comp_a_name if tool_score_a < tool_score_b else comp_b_name
        },
        {
            "dimension": "Claim Veracity",
            "metric": "Verified Claims Ratio",
            "unit": "%",
            "target_a_value": f"{(verified_a / total_cl_a * 100.0):.0f}% ({verified_a}/{total_cl_a})",
            "target_b_value": f"{(verified_b / total_cl_b * 100.0):.0f}% ({verified_b}/{total_cl_b})",
            "delta": f"{(verified_a / total_cl_a - verified_b / total_cl_b) * 100.0:+.0f}%",
            "advantage": comp_a_name if (verified_a / total_cl_a) > (verified_b / total_cl_b) else comp_b_name
        }
    ]
    
    return {
        "comparison_title": f"Technical Diligence Comparative Review: {comp_a_name} vs {comp_b_name}",
        "target_a": {
            "id": company_a_id,
            "name": comp_a_name,
            "traces": auto_a.get("total_traces", 0)
        },
        "target_b": {
            "id": company_b_id,
            "name": comp_b_name,
            "traces": auto_b.get("total_traces", 0)
        },
        "dimension_winners": {
            "autonomy": autonomy_winner,
            "economics": economics_winner,
            "resilience": resilience_winner,
            "governance_and_safety": gov_winner
        },
        "matrix": comparison_matrix
    }
