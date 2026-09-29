from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import Trace, Span, HumanIntervention

HIGH_PRIVILEGE_SYSTEM_KEYWORDS = {
    "bash", "shell", "exec", "terminal", "python", "code_interpreter",
    "eval", "command", "system_call", "sh"
}

HIGH_PRIVILEGE_MUTATION_KEYWORDS = {
    "sql_write", "db_write", "database_update", "file_write", "delete",
    "drop_table", "modify", "update_record", "patch_data", "insert"
}

MEDIUM_PRIVILEGE_COMM_KEYWORDS = {
    "send_email", "webhook", "slack_notify", "http_post", "api_call",
    "stripe_charge", "payment", "publish_event", "notify", "external_api"
}

def classify_tool_privilege(tool_name: str) -> str:
    """Classifies tool into CRITICAL, HIGH, MEDIUM, or LOW privilege."""
    if not tool_name:
        return "LOW"
    t_lower = tool_name.lower().replace("-", "_").replace(" ", "_")
    
    for kw in HIGH_PRIVILEGE_SYSTEM_KEYWORDS:
        if kw in t_lower:
            return "CRITICAL"
            
    for kw in HIGH_PRIVILEGE_MUTATION_KEYWORDS:
        if kw in t_lower:
            return "HIGH"
            
    for kw in MEDIUM_PRIVILEGE_COMM_KEYWORDS:
        if kw in t_lower:
            return "MEDIUM"
            
    return "LOW"

def analyze_tool_execution_risk(db: Session, company_id: str) -> Dict[str, Any]:
    """
    Analyzes agentic tool invocations, privilege escalation risks,
    sandbox boundaries, failure rates, and unconstrained execution patterns.
    """
    total_traces = db.query(func.count(Trace.id)).filter(Trace.company_id == company_id).scalar() or 0
    if total_traces == 0:
        return {
            "total_tool_calls": 0,
            "unique_tools_count": 0,
            "tool_invocation_rate_per_trace": 0.0,
            "tool_failure_count": 0,
            "tool_failure_rate_pct": 0.0,
            "critical_privilege_calls": 0,
            "high_privilege_calls": 0,
            "medium_privilege_calls": 0,
            "low_privilege_calls": 0,
            "high_or_critical_privilege_pct": 0.0,
            "unconstrained_execution_traces_count": 0,
            "unconstrained_execution_rate_pct": 0.0,
            "tool_risk_score": 0.0,
            "risk_level": "LOW",
            "tool_inventory": []
        }
        
    tool_spans = db.query(Span).join(Trace, Span.trace_id == Trace.id)\
        .filter(Trace.company_id == company_id, Span.span_kind == "tool").all()
        
    total_tool_calls = len(tool_spans)
    if total_tool_calls == 0:
        return {
            "total_tool_calls": 0,
            "unique_tools_count": 0,
            "tool_invocation_rate_per_trace": 0.0,
            "tool_failure_count": 0,
            "tool_failure_rate_pct": 0.0,
            "critical_privilege_calls": 0,
            "high_privilege_calls": 0,
            "medium_privilege_calls": 0,
            "low_privilege_calls": 0,
            "high_or_critical_privilege_pct": 0.0,
            "unconstrained_execution_traces_count": 0,
            "unconstrained_execution_rate_pct": 0.0,
            "tool_risk_score": 0.0,
            "risk_level": "LOW",
            "tool_inventory": []
        }
        
    # Group tool metrics
    inventory_map: Dict[str, Dict[str, Any]] = {}
    traces_with_high_priv: set = set()
    traces_with_tools: set = set()
    
    crit_count = 0
    high_count = 0
    med_count = 0
    low_count = 0
    failure_count = 0
    
    for s in tool_spans:
        t_name = s.tool_name or s.name or "unknown_tool"
        priv = classify_tool_privilege(t_name)
        traces_with_tools.add(s.trace_id)
        
        if priv == "CRITICAL":
            crit_count += 1
            traces_with_high_priv.add(s.trace_id)
        elif priv == "HIGH":
            high_count += 1
            traces_with_high_priv.add(s.trace_id)
        elif priv == "MEDIUM":
            med_count += 1
        else:
            low_count += 1
            
        if s.is_error:
            failure_count += 1
            
        if t_name not in inventory_map:
            inventory_map[t_name] = {
                "tool_name": t_name,
                "privilege_level": priv,
                "invocation_count": 0,
                "error_count": 0,
                "total_duration_ms": 0.0
            }
        inv = inventory_map[t_name]
        inv["invocation_count"] += 1
        if s.is_error:
            inv["error_count"] += 1
        inv["total_duration_ms"] += (s.duration_ms or 0.0)
        
    # Check human oversight on high-privilege traces
    unconstrained_traces = 0
    if traces_with_high_priv:
        traces_with_human = set(
            row[0] for row in db.query(Trace.id).filter(
                Trace.company_id == company_id,
                Trace.id.in_(list(traces_with_high_priv)),
                Trace.has_human_intervention == True
            ).all()
        )
        unconstrained_traces = len(traces_with_high_priv - traces_with_human)
        
    # Format inventory
    inventory = []
    for t_name, data in inventory_map.items():
        inv_count = data["invocation_count"]
        err_count = data["error_count"]
        avg_lat = (data["total_duration_ms"] / inv_count) if inv_count > 0 else 0.0
        inventory.append({
            "tool_name": t_name,
            "privilege_level": data["privilege_level"],
            "invocation_count": inv_count,
            "error_count": err_count,
            "error_rate_pct": round((err_count / inv_count * 100.0), 1) if inv_count > 0 else 0.0,
            "avg_latency_ms": round(avg_lat, 1)
        })
    inventory.sort(key=lambda x: x["invocation_count"], reverse=True)
    
    # Deterministic Risk Score: 0 to 100
    # Penalty components:
    # 1. Critical tool calls (up to 30 pts)
    # 2. High tool calls (up to 20 pts)
    # 3. Unconstrained execution rate (up to 30 pts)
    # 4. Tool failure rate (up to 20 pts)
    crit_ratio = crit_count / total_tool_calls
    high_ratio = high_count / total_tool_calls
    err_rate_pct = (failure_count / total_tool_calls * 100.0) if total_tool_calls > 0 else 0.0
    unconstrained_pct = (unconstrained_traces / total_traces * 100.0) if total_traces > 0 else 0.0
    
    risk_score = (crit_ratio * 40.0) + (high_ratio * 20.0) + (min(unconstrained_pct, 100.0) * 0.25) + (min(err_rate_pct, 50.0) * 0.3)
    risk_score = round(min(100.0, max(0.0, risk_score)), 1)
    
    if risk_score >= 60.0:
        risk_level = "CRITICAL"
    elif risk_score >= 40.0:
        risk_level = "ELEVATED"
    elif risk_score >= 20.0:
        risk_level = "MODERATE"
    else:
        risk_level = "LOW"
        
    return {
        "total_tool_calls": total_tool_calls,
        "unique_tools_count": len(inventory),
        "tool_invocation_rate_per_trace": round(total_tool_calls / total_traces, 2),
        "tool_failure_count": failure_count,
        "tool_failure_rate_pct": round(err_rate_pct, 1),
        "critical_privilege_calls": crit_count,
        "high_privilege_calls": high_count,
        "medium_privilege_calls": med_count,
        "low_privilege_calls": low_count,
        "high_or_critical_privilege_pct": round(((crit_count + high_count) / total_tool_calls * 100.0), 1),
        "unconstrained_execution_traces_count": unconstrained_traces,
        "unconstrained_execution_rate_pct": round(unconstrained_pct, 1),
        "tool_risk_score": risk_score,
        "risk_level": risk_level,
        "tool_inventory": inventory
    }
