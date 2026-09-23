from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.db.models import Trace, Span, CostEvent

def analyze_provider_dependencies(db: Session, company_id: str) -> Dict[str, Any]:
    """
    Calculates Herfindahl-Hirschman Index (HHI) and evidence-first Potential Single Point of Failure (PSPOF) assessments.
    """
    provider_costs = db.query(
        CostEvent.provider_name,
        func.sum(CostEvent.cost_usd),
        func.count(CostEvent.id)
    ).join(Trace, CostEvent.trace_id == Trace.id)\
     .filter(Trace.company_id == company_id)\
     .group_by(CostEvent.provider_name).all()
     
    total_cost = sum(cost for _, cost, _ in provider_costs)
    total_traces = db.query(func.count(Trace.id)).filter(Trace.company_id == company_id).scalar() or 0
    
    if total_cost == 0:
        return {
            "hhi_score": 0.0,
            "concentration_level": "UNKNOWN",
            "providers": [],
            "potential_spofs": [],
            "raw_metrics": {"hhi_score": 0.0, "total_measured_cost_usd": 0.0},
            "interpretation": "No provider expenditure observed in available telemetry.",
            "potential_implications": "Provider dependency cannot be evaluated."
        }
        
    providers_list = []
    hhi_score = 0.0
    
    for provider, cost, count in provider_costs:
        share = cost / float(total_cost)
        hhi_score += (share ** 2)
        
        providers_list.append({
            "provider_name": provider,
            "cost_usd": round(cost, 4),
            "share_pct": round(share * 100.0, 2),
            "event_count": count
        })
        
    providers_list.sort(key=lambda x: x["share_pct"], reverse=True)
    
    # Raw Metric vs Interpretation
    if hhi_score >= 0.60:
        conc_level = "HIGH_CONCENTRATION"
        interp = f"Observed inference expenditure is heavily concentrated in a single provider ({providers_list[0]['provider_name']} represents {providers_list[0]['share_pct']}% of cost)."
        impl = "Provider outages, API deprecations, or price adjustments by the primary vendor could materially impact system operations."
    elif hhi_score >= 0.30:
        conc_level = "MODERATE_CONCENTRATION"
        interp = "Inference expenditure is distributed across a primary and secondary provider."
        impl = "Partial redundancy exists, though major operational shifts in the primary provider would require workflow adjustments."
    else:
        conc_level = "DIVERSIFIED"
        interp = "Inference expenditure is balanced across multiple independent providers."
        impl = "System exhibits multi-provider load balancing and lower operational vendor risk."
        
    # Potential Single Point of Failure (PSPOF) Evidence Evaluation
    potential_spofs = []
    
    # Check Model Providers (> 65% share)
    for p in providers_list:
        if p["share_pct"] >= 65.0:
            secondary_providers = [o["provider_name"] for o in providers_list if o["provider_name"] != p["provider_name"]]
            fallback_configured = len(secondary_providers) > 0
            
            # Check if telemetry ever shows fallback routing
            fallback_observed = len(secondary_providers) > 0 and any(o["share_pct"] > 5.0 for o in providers_list if o["provider_name"] != p["provider_name"])
            
            # Check errors observed for this provider
            provider_errors = db.query(Span.error_message).join(Trace, Span.trace_id == Trace.id)\
                .filter(Trace.company_id == company_id, Span.gen_ai_system == p["provider_name"], Span.is_error == True).all()
            err_list = list(set(e[0] for e in provider_errors if e[0]))
            
            potential_spofs.append({
                "component_name": p["provider_name"],
                "component_type": "Foundation Model Provider",
                "dependency_share_pct": p["share_pct"],
                "fallback_observed": fallback_observed,
                "fallback_configured": fallback_configured,
                "fallback_tested": fallback_observed and len(err_list) > 0,
                "failure_evidence": err_list if err_list else ["No runtime API errors observed in window"],
                "observation_coverage": f"{total_traces} workflow traces in Last 30 Days",
                "risk_status": "POTENTIAL_SPOF_MITIGATED" if fallback_observed else "POTENTIAL_SPOF_ACTIVE"
            })
            
    # Check External Tools (> 70% of traces rely on single tool)
    tool_counts = db.query(
        Span.tool_name,
        func.count(func.distinct(Span.trace_id)),
        func.sum(case((Span.is_error == True, 1), else_=0))
    ).join(Trace, Span.trace_id == Trace.id)\
     .filter(Trace.company_id == company_id, Span.tool_name != None)\
     .group_by(Span.tool_name).all()
     
    has_fallback_tool = any("fallback" in (t[0] or "").lower() for t in tool_counts)
    
    for t_name, trace_cnt, err_cnt in tool_counts:
        if not t_name or "fallback" in t_name.lower():
            continue
        share_traces = round((trace_cnt / float(total_traces)) * 100.0, 2) if total_traces > 0 else 0.0
        if share_traces >= 70.0:
            err_spans = db.query(Span.error_message).join(Trace, Span.trace_id == Trace.id)\
                .filter(Trace.company_id == company_id, Span.tool_name == t_name, Span.is_error == True).all()
            t_errs = list(set(e[0] for e in err_spans if e[0]))
            
            potential_spofs.append({
                "component_name": t_name,
                "component_type": "External Integration Tool",
                "dependency_share_pct": share_traces,
                "fallback_observed": has_fallback_tool,
                "fallback_configured": has_fallback_tool,
                "fallback_tested": has_fallback_tool and (err_cnt > 0),
                "failure_evidence": t_errs if t_errs else ["No tool execution failures observed"],
                "observation_coverage": f"{trace_cnt}/{total_traces} traces ({share_traces}%) invoke this tool",
                "risk_status": "POTENTIAL_SPOF_MITIGATED" if has_fallback_tool else "POTENTIAL_SPOF_ACTIVE"
            })
        
    return {
        "raw_metrics": {
            "hhi_score": round(hhi_score, 4),
            "total_measured_cost_usd": round(total_cost, 4),
            "provider_count": len(providers_list)
        },
        "hhi_score": round(hhi_score, 4),
        "concentration_level": conc_level,
        "providers": providers_list,
        "potential_spofs": potential_spofs,
        "interpretation": interp,
        "potential_implications": impl
    }
