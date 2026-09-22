import math
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import Trace, CostEvent, CostStatus

def percentile(N: List[float], percent: float) -> float:
    if not N:
        return 0.0
    k = (len(N) - 1) * percent
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return N[int(k)]
    d0 = N[int(f)] * (c - k)
    d1 = N[int(c)] * (k - f)
    return d0 + d1

def analyze_unit_economics(db: Session, company_id: str) -> Dict[str, Any]:
    """
    Computes telemetry-attributable unit economics and explicit cost status breakdowns.
    """
    traces = db.query(Trace.duration_ms, Trace.total_cost, Trace.status_code, Trace.has_unpriced_model).filter(
        Trace.company_id == company_id
    ).all()
    
    total_tasks = len(traces)
    if total_tasks == 0:
        return {
            "total_tasks": 0,
            "total_measured_cost_usd": 0.0,
            "telemetry_attributable_cost_per_task_usd": 0.0,
            "cost_status": CostStatus.NOT_ESTABLISHED.value,
            "cost_breakdown": {},
            "latency_ms": {"p50": 0, "p95": 0, "p99": 0}
        }
        
    total_cost = sum(t.total_cost for t in traces)
    has_unpriced = any(t.has_unpriced_model for t in traces)
    overall_cost_status = CostStatus.UNKNOWN.value if has_unpriced else CostStatus.MEASURED.value
    
    successful_tasks = sum(1 for t in traces if t.status_code == "OK")
    
    cost_per_task = total_cost / float(total_tasks)
    cost_per_successful_task = total_cost / float(successful_tasks) if successful_tasks > 0 else 0.0
    
    # Latency percentiles
    durations = sorted([t.duration_ms for t in traces])
    p50 = percentile(durations, 0.50)
    p95 = percentile(durations, 0.95)
    p99 = percentile(durations, 0.99)
    
    # Categorized Cost Breakdown with explicit CostStatus
    cost_events = db.query(
        CostEvent.cost_category,
        func.sum(CostEvent.cost_usd)
    ).join(Trace, CostEvent.trace_id == Trace.id)\
     .filter(Trace.company_id == company_id)\
     .group_by(CostEvent.cost_category).all()
     
    cat_breakdown = {}
    for category, sum_cost in cost_events:
        cat_breakdown[category] = {
            "total_cost_usd": round(sum_cost, 4),
            "percentage_of_measured": round((sum_cost / total_cost) * 100.0, 2) if total_cost > 0 else 0.0,
            "cost_status": CostStatus.UNKNOWN.value if (has_unpriced and category == "inference") else CostStatus.MEASURED.value
        }
        
    # Unmeasured cost dimensions
    cat_breakdown["infrastructure"] = {"total_cost_usd": 0.0, "cost_status": CostStatus.UNKNOWN.value, "note": "Unmeasured in current telemetry"}
    cat_breakdown["human_operations"] = {"total_cost_usd": 0.0, "cost_status": CostStatus.UNKNOWN.value, "note": "Unmeasured in current telemetry"}
    cat_breakdown["governance_legal"] = {"total_cost_usd": 0.0, "cost_status": CostStatus.NOT_ESTABLISHED.value, "note": "Outside telemetry scope"}
    
    return {
        "total_tasks": total_tasks,
        "successful_tasks": successful_tasks,
        "total_measured_cost_usd": round(total_cost, 4),
        "telemetry_attributable_cost_per_task_usd": round(cost_per_task, 6),
        "telemetry_attributable_cost_per_successful_task_usd": round(cost_per_successful_task, 6),
        "overall_cost_status": overall_cost_status,
        "pricing_version": "v2026_09",
        "cost_breakdown": cat_breakdown,
        "latency_ms": {
            "p50": round(p50, 1),
            "p95": round(p95, 1),
            "p99": round(p99, 1)
        }
    }
