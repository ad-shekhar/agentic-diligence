from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import Trace, Span, CostEvent

def analyze_evaluation_overhead(db: Session, company_id: str) -> Dict[str, Any]:
    """
    Computes Trust Tax rate (Evaluation Overhead Rate) and Evaluation Coverage deterministically.
    """
    total_traces = db.query(func.count(Trace.id)).filter(Trace.company_id == company_id).scalar() or 0
    if total_traces == 0:
        return {
            "eval_coverage_pct": 0.0,
            "trust_tax_rate_pct": 0.0,
            "inference_cost_usd": 0.0,
            "evaluation_cost_usd": 0.0,
            "evaluation_status": "INSUFFICIENT_TELEMETRY",
            "insufficient_coverage_flag": True
        }
        
    eval_spans_count = db.query(func.count(func.distinct(Span.trace_id))).join(Trace, Span.trace_id == Trace.id)\
        .filter(Trace.company_id == company_id, Span.span_kind == "evaluation").scalar() or 0
        
    coverage_pct = (eval_spans_count / float(total_traces)) * 100.0
    
    inf_cost = db.query(func.sum(CostEvent.cost_usd)).join(Trace, CostEvent.trace_id == Trace.id)\
        .filter(Trace.company_id == company_id, CostEvent.cost_category == "inference").scalar() or 0.0
        
    eval_cost = db.query(func.sum(CostEvent.cost_usd)).join(Trace, CostEvent.trace_id == Trace.id)\
        .filter(Trace.company_id == company_id, CostEvent.cost_category == "evaluation").scalar() or 0.0
        
    trust_tax_rate = (eval_cost / float(inf_cost)) * 100.0 if inf_cost > 0 else 0.0
    
    # Flag insufficient evaluation coverage (< 20%)
    insufficient_flag = coverage_pct < 20.0
    eval_status = "INSUFFICIENT_EVALUATION_COVERAGE" if insufficient_flag else "ADEQUATE_EVALUATION_COVERAGE"
    
    return {
        "eval_traces_count": eval_spans_count,
        "total_traces": total_traces,
        "eval_coverage_pct": round(coverage_pct, 2),
        "inference_cost_usd": round(inf_cost, 4),
        "evaluation_cost_usd": round(eval_cost, 4),
        "trust_tax_rate_pct": round(trust_tax_rate, 2),
        "evaluation_status": eval_status,
        "insufficient_coverage_flag": insufficient_flag,
        "note": "A low Trust Tax rate accompanied by low evaluation coverage indicates risk of insufficient automated quality control." if insufficient_flag else "Evaluation spans observed across active workflows."
    }
