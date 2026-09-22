from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import Trace, CostEvent

def analyze_provider_dependencies(db: Session, company_id: str) -> Dict[str, Any]:
    """
    Calculates Herfindahl-Hirschman Index (HHI) and separates raw metrics from contextual interpretations.
    """
    provider_costs = db.query(
        CostEvent.provider_name,
        func.sum(CostEvent.cost_usd),
        func.count(CostEvent.id)
    ).join(Trace, CostEvent.trace_id == Trace.id)\
     .filter(Trace.company_id == company_id)\
     .group_by(CostEvent.provider_name).all()
     
    total_cost = sum(cost for _, cost, _ in provider_costs)
    if total_cost == 0:
        return {
            "hhi_score": 0.0,
            "concentration_level": "UNKNOWN",
            "providers": [],
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
        
    return {
        "raw_metrics": {
            "hhi_score": round(hhi_score, 4),
            "total_measured_cost_usd": round(total_cost, 4),
            "provider_count": len(providers_list)
        },
        "hhi_score": round(hhi_score, 4),
        "concentration_level": conc_level,
        "providers": providers_list,
        "interpretation": interp,
        "potential_implications": impl
    }
