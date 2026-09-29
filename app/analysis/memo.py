from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.analysis.intervention import analyze_human_intervention
from app.analysis.economics import analyze_unit_economics
from app.analysis.evaluation import analyze_evaluation_overhead
from app.analysis.dependency import analyze_provider_dependencies
from app.analysis.cascade import analyze_failure_cascades
from app.analysis.tool_risk import analyze_tool_execution_risk
from app.analysis.defensibility import analyze_defensibility_and_moat
from app.analysis.stress_test import simulate_stress_test_economics
from app.db.models import Claim, Company

def generate_investment_committee_memo(db: Session, company_id: str) -> Dict[str, Any]:
    """
    Synthesizes technical diligence metrics into an institutional-grade
    Executive Diligence Memo with Red/Yellow/Green flag classification,
    Acquisition Risk Score, Deal Recommendation, and Remediation Playbook.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    company_name = company.name if company else "Target AI Target"
    
    interv = analyze_human_intervention(db, company_id)
    econ = analyze_unit_economics(db, company_id)
    eval_res = analyze_evaluation_overhead(db, company_id)
    dep = analyze_provider_dependencies(db, company_id)
    casc = analyze_failure_cascades(db, company_id)
    tool_risk = analyze_tool_execution_risk(db, company_id)
    moat = analyze_defensibility_and_moat(db, company_id)
    stress = simulate_stress_test_economics(db, company_id)
    
    claims = db.query(Claim).filter(Claim.company_id == company_id).all()
    
    red_flags: List[Dict[str, str]] = []
    yellow_flags: List[Dict[str, str]] = []
    green_flags: List[Dict[str, str]] = []
    
    # --- 1. Audit Flag Evaluation ---
    
    # Claim contradictions
    contra_claims = [c for c in claims if str(c.verification_status) == "VerificationStatus.CONTRADICTED" or c.verification_status == "CONTRADICTED"]
    if contra_claims:
        for c in contra_claims:
            red_flags.append({
                "flag_id": "RF-CLAIM-01",
                "category": "Claim Integrity",
                "severity": "CRITICAL",
                "title": f"Contradicted Pitch Deck Claim: {c.category.title()}",
                "detail": f"Claimed '{c.claim_text}', but telemetry demonstrated '{c.observed_value}'. {c.verification_reason}"
            })
            
    # Autonomy & HIR
    hir_pct = interv.get("human_intervention_rate_pct", 0.0)
    auto_pct = interv.get("autonomous_rate_pct", 100.0 - hir_pct)
    if hir_pct > 40.0:
        red_flags.append({
            "flag_id": "RF-AUTO-01",
            "category": "Autonomy",
            "severity": "HIGH",
            "title": f"Severe Human Dependency ({hir_pct:.1f}% HIR)",
            "detail": "Over 40% of workflow tasks require human intervention. Core product operates as human-in-the-loop service rather than autonomous software."
        })
    elif hir_pct > 20.0:
        yellow_flags.append({
            "flag_id": "YF-AUTO-01",
            "category": "Autonomy",
            "severity": "MEDIUM",
            "title": f"Moderate Human Intervention ({hir_pct:.1f}% HIR)",
            "detail": "Approximately 1 in 5 customer workflows triggers operator intervention, adding ongoing labor overhead."
        })
    else:
        green_flags.append({
            "flag_id": "GF-AUTO-01",
            "category": "Autonomy",
            "title": f"High Autonomous Completion ({auto_pct:.1f}%)",
            "detail": "Verified true autonomy exceeds 80% without manual operator takeover, confirming scalable software leverage."
        })
        
    # Tool Execution & Privilege
    crit_tool_calls = tool_risk.get("critical_privilege_calls", 0)
    if crit_tool_calls > 0:
        red_flags.append({
            "flag_id": "RF-SEC-01",
            "category": "Security & Sandbox",
            "severity": "CRITICAL",
            "title": f"Unconstrained Critical Privilege Tool Invocations ({crit_tool_calls} calls)",
            "detail": "Agent invokes shell/bash/code execution tools without verifiable isolation, posing systemic RCE and blast radius hazards."
        })
    elif tool_risk.get("high_privilege_calls", 0) > 0:
        yellow_flags.append({
            "flag_id": "YF-SEC-01",
            "category": "Security & Sandbox",
            "severity": "MEDIUM",
            "title": "Database Mutation Tools Present",
            "detail": "Agent possesses write/delete privileges to production databases. Strict guardrails must be validated."
        })
    else:
        green_flags.append({
            "flag_id": "GF-SEC-01",
            "category": "Security & Sandbox",
            "title": "Low Tool Execution Blast Radius",
            "detail": "Tool privileges are scoped to read-only customer APIs and vector search without unconstrained execution risks."
        })
        
    # Economics & Gross Margins
    stressed_margin = stress["stressed_economics"]["gross_margin_pct"]
    if stressed_margin < 0.0:
        red_flags.append({
            "flag_id": "RF-ECON-01",
            "category": "Unit Economics",
            "severity": "CRITICAL",
            "title": "Negative Fully-Loaded Unit Margins",
            "detail": f"When human operator costs are accounted for, gross margin is negative ({stressed_margin}%). Unchecked volume growth will compound operational losses."
        })
    elif stressed_margin < 50.0:
        yellow_flags.append({
            "flag_id": "YF-ECON-01",
            "category": "Unit Economics",
            "severity": "MEDIUM",
            "title": f"Gross Margin Compression Risk ({stressed_margin}%)",
            "detail": "Gross margin falls below SaaS baseline (70%) under stressed model pricing and human operational overhead."
        })
    else:
        green_flags.append({
            "flag_id": "GF-ECON-01",
            "category": "Unit Economics",
            "title": f"Resilient Gross Margins ({stressed_margin}%)",
            "detail": "Fully-loaded unit economics demonstrate viable software margins under volume and model price shocks."
        })
        
    # Provider Concentration & SPOF
    hhi = dep.get("hhi_score", 0)
    if hhi > 7500:
        yellow_flags.append({
            "flag_id": "YF-DEP-01",
            "category": "Architecture & Dependency",
            "severity": "HIGH",
            "title": f"Extreme Single-Provider Lock-In (HHI {hhi})",
            "detail": "Over 90% of model spend depends on a single vendor with unproven fallback routing during API downtime."
        })
    elif hhi < 4500:
        green_flags.append({
            "flag_id": "GF-DEP-01",
            "category": "Architecture & Dependency",
            "title": f"Diversified Multi-Model Orchestration (HHI {hhi})",
            "detail": "Workload is balanced across multiple providers/weights, mitigating single vendor outage and price hike risks."
        })
        
    # Defensibility & Moat
    moat_score = moat.get("moat_score", 0.0)
    moat_class = moat.get("moat_classification", "COMMODITY_WRAPPER")
    if moat_class == "COMMODITY_WRAPPER":
        red_flags.append({
            "flag_id": "RF-MOAT-01",
            "category": "Defensibility & Moat",
            "severity": "HIGH",
            "title": "Commodity Wrapper Architecture (Moat Score: " + str(moat_score) + "/100)",
            "detail": "Minimal proprietary scaffolding, zero fine-tuned weights, and low switching barriers. Easily replicated by competitors in <2 months."
        })
    elif moat_class in ["PROPRIETARY_COMPOUND_SYSTEM", "DEEP_DEFENSIBLE_MOAT"]:
        green_flags.append({
            "flag_id": "GF-MOAT-01",
            "category": "Defensibility & Moat",
            "title": f"Defensible Compound Architecture ({moat_class.replace('_', ' ').title()})",
            "detail": f"Proprietary cognitive scaffolding, enterprise connectors, and evaluation flywheel create high replication barrier (Moat Score: {moat_score}/100)."
        })
        
    # Cascades
    casc_freq = casc.get("cascade_frequency_pct", 0.0)
    if casc_freq > 20.0:
        yellow_flags.append({
            "flag_id": "YF-CASC-01",
            "category": "Operational Reliability",
            "severity": "MEDIUM",
            "title": f"Frequent Failure Cascade Recovery Loops ({casc_freq}% of traces)",
            "detail": f"Agent frequently encounters tool timeouts and enters retry loops ({casc.get('avg_cost_multiplier_on_failure')}x cost multiplier)."
        })
        
    # Evaluation coverage
    eval_cov = eval_res.get("eval_coverage_pct", 0.0)
    if eval_cov < 20.0:
        yellow_flags.append({
            "flag_id": "YF-EVAL-01",
            "category": "Governance & Quality Control",
            "severity": "MEDIUM",
            "title": f"Low Automated Evaluation Coverage ({eval_cov}% of traces)",
            "detail": "Fewer than 20% of traces run automated quality or guardrail evaluations, leaving production outputs largely unmonitored."
        })
        
    # --- 2. Composite Diligence Risk Score (0-100) ---
    # Higher score = higher risk
    risk_score = 15.0 # baseline
    risk_score += len(red_flags) * 22.0
    risk_score += len(yellow_flags) * 7.0
    risk_score -= len(green_flags) * 6.0
    
    # Bound 0-100
    risk_score = max(5.0, min(95.0, risk_score))
    risk_score = round(risk_score, 1)
    
    # Deal Recommendation
    if len(red_flags) >= 2 or risk_score >= 70.0:
        verdict = "DO_NOT_PROCEED"
        verdict_summary = (
            f"DO NOT PROCEED: Serious structural deficiencies identified in {company_name}. "
            "Contradicted founder claims, negative unit margins under loaded labor, or critical security vulnerabilities "
            "represent severe acquisition hazards that cannot be resolved without complete architectural rebuild."
        )
    elif len(red_flags) == 1 or risk_score >= 45.0:
        verdict = "HIGH_RISK_CAUTION"
        verdict_summary = (
            f"HIGH RISK / CAUTION: Elevated diligence concerns for {company_name}. "
            "Proceed only with valuation discount, aggressive escrow reserves, and mandatory pre-closing remediation "
            "of highlighted red and yellow flags."
        )
    elif len(yellow_flags) >= 2 or risk_score >= 25.0:
        verdict = "CONDITIONAL_REMEDIATION_REQUIRED"
        verdict_summary = (
            f"CONDITIONAL APPROVAL: Fundamentally sound architecture at {company_name} with identifiable operational risks. "
            "Recommend proceeding subject to post-close technical remediation playbook execution (tool sandboxing, "
            "provider diversification, and evaluation coverage expansion)."
        )
    else:
        verdict = "RECOMMENDED"
        verdict_summary = (
            f"RECOMMENDED: Exemplary technical due diligence audit for {company_name}. "
            "Verified pitch claims, high autonomous completion rate, resilient multi-model unit economics, "
            "and defensible proprietary scaffolding."
        )
        
    # --- 3. 100-Day Technical Remediation Playbook ---
    remediation_playbook = [
        {
            "priority": "P0 (Pre-Closing / Day 1-14)",
            "initiative": "Tool Privilege Sandboxing & RCE Isolation",
            "action": "Isolate high-privilege execution spans into ephemeral gVisor/WASM sandboxes with strict egress filtering.",
            "kpi_target": "Zero unconstrained shell/interpreter calls"
        },
        {
            "priority": "P1 (Day 15-45)",
            "initiative": "Operational Human-in-the-Loop Cost Reduction",
            "action": "Fine-tune smaller models on human intervention logs to automate repetitive operator escalation paths.",
            "kpi_target": "Reduce HIR by 50% within 45 days"
        },
        {
            "priority": "P2 (Day 46-75)",
            "initiative": "Multi-Provider Failover & Routing Guardrails",
            "action": "Deploy intelligent model gateway with automated circuit breakers and secondary provider fallback routing.",
            "kpi_target": "Reduce HHI below 4,000; guarantee <500ms failover"
        },
        {
            "priority": "P3 (Day 76-100)",
            "initiative": "Continuous Evaluation Flywheel Instrumentation",
            "action": "Instrument automated LLM-as-a-judge evaluation spans on 100% of production workflows.",
            "kpi_target": "Evaluation coverage >85% with automated regression alert"
        }
    ]
    
    return {
        "company_name": company_name,
        "company_id": company_id,
        "diligence_risk_score": risk_score,
        "risk_classification": "CRITICAL" if risk_score >= 70 else ("ELEVATED" if risk_score >= 45 else ("MODERATE" if risk_score >= 25 else "LOW")),
        "deal_verdict": verdict,
        "executive_verdict_summary": verdict_summary,
        "flags_summary": {
            "red_flags_count": len(red_flags),
            "yellow_flags_count": len(yellow_flags),
            "green_flags_count": len(green_flags)
        },
        "red_flags": red_flags,
        "yellow_flags": yellow_flags,
        "green_flags": green_flags,
        "remediation_playbook": remediation_playbook
    }
