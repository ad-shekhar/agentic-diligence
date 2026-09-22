from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import Trace, Span, HumanIntervention, InterventionDetectionMethod

def analyze_human_intervention(db: Session, company_id: str) -> Dict[str, Any]:
    """
    Analyzes human intervention rate (HIR), distinguishing explicitly observed vs inferred heuristics.
    """
    total_traces = db.query(func.count(Trace.id)).filter(Trace.company_id == company_id).scalar() or 0
    if total_traces == 0:
        return {
            "total_traces": 0,
            "autonomous_traces": 0,
            "human_traces": 0,
            "explicitly_observed_human_traces": 0,
            "inferred_heuristic_human_traces": 0,
            "human_intervention_rate_pct": 0.0,
            "autonomous_rate_pct": 0.0,
            "data_coverage": {
                "telemetry_population": 0,
                "analyzed_traces": 0,
                "missing_data_pct": 0.0,
                "observation_statement": "No available telemetry traces to analyze."
            },
            "breakdown": {}
        }
        
    human_traces = db.query(func.count(Trace.id)).filter(
        Trace.company_id == company_id,
        Trace.has_human_intervention == True
    ).scalar() or 0
    
    # Distinguish Explicit vs Inferred
    explicit_count = db.query(func.count(func.distinct(HumanIntervention.trace_id))).join(Trace, HumanIntervention.trace_id == Trace.id)\
        .filter(Trace.company_id == company_id, HumanIntervention.detected_via == InterventionDetectionMethod.OBSERVED_TELEMETRY).scalar() or 0
        
    inferred_count = human_traces - explicit_count
    
    autonomous_traces = total_traces - human_traces
    hir = (human_traces / float(total_traces)) * 100.0
    auto_rate = (autonomous_traces / float(total_traces)) * 100.0
    
    # Detailed breakdown
    interventions = db.query(
        HumanIntervention.intervention_type,
        HumanIntervention.detected_via,
        func.count(HumanIntervention.id),
        func.avg(HumanIntervention.reaction_time_seconds)
    ).join(Trace, HumanIntervention.trace_id == Trace.id)\
     .filter(Trace.company_id == company_id)\
     .group_by(HumanIntervention.intervention_type, HumanIntervention.detected_via).all()
     
    breakdown = {}
    for int_type, det_via, count, avg_react in interventions:
        det_str = det_via.value if hasattr(det_via, "value") else str(det_via)
        key = f"{int_type} ({det_str})"
        breakdown[key] = {
            "count": count,
            "detection_method": det_str,
            "percentage": round((count / float(total_traces)) * 100.0, 2),
            "avg_reaction_time_seconds": round(avg_react or 0.0, 1)
        }
        
    obs_statement = (
        f"In the available dataset of {total_traces} instrumented traces, "
        f"{autonomous_traces} ({auto_rate:.1f}%) contained no detected human intervention signals. "
        f"Human intervention was detected in {human_traces} ({hir:.1f}%) traces "
        f"({explicit_count} explicitly observed in telemetry, {inferred_count} inferred via reaction latency heuristics)."
    )
    
    return {
        "total_traces": total_traces,
        "autonomous_traces": autonomous_traces,
        "human_traces": human_traces,
        "explicitly_observed_human_traces": explicit_count,
        "inferred_heuristic_human_traces": inferred_count,
        "human_intervention_rate_pct": round(hir, 2),
        "autonomous_rate_pct": round(auto_rate, 2),
        "data_coverage": {
            "telemetry_population": total_traces,
            "analyzed_traces": total_traces,
            "missing_data_pct": 0.0,
            "observation_statement": obs_statement
        },
        "breakdown": breakdown
    }
