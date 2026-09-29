from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models import Trace, Span

def analyze_defensibility_and_moat(db: Session, company_id: str) -> Dict[str, Any]:
    """
    Evaluates whether the target company possesses a defensible AI moat
    or is merely a thin wrapper around commodity third-party LLM APIs.
    
    Dimensions assessed:
    1. Scaffolding Depth & Cognitive Complexity (orchestration vs raw prompts)
    2. Model Sovereignty & Weight Ownership (self-hosted/fine-tuned vs commodity APIs)
    3. Custom Tool & Domain Integration Assets (proprietary vs public APIs)
    4. Data Flywheel & Continuous Evaluation Loop (active feedback telemetry)
    5. Replication Barrier (engineering time & capital required to clone)
    """
    total_traces = db.query(func.count(Trace.id)).filter(Trace.company_id == company_id).scalar() or 0
    if total_traces == 0:
        return {
            "moat_score": 0.0,
            "moat_classification": "COMMODITY_WRAPPER",
            "scaffolding_complexity_score": 0.0,
            "weight_sovereignty_score": 0.0,
            "tool_integration_score": 0.0,
            "data_flywheel_score": 0.0,
            "estimated_replication_months": 1.0,
            "estimated_replication_cost_usd": 75000,
            "breakdown": {},
            "verdict_summary": "Insufficient telemetry to evaluate defensibility."
        }
        
    spans = db.query(Span).join(Trace, Span.trace_id == Trace.id)\
        .filter(Trace.company_id == company_id).all()
        
    total_spans = len(spans)
    agent_spans = [s for s in spans if s.span_kind == "agent"]
    llm_spans = [s for s in spans if s.span_kind == "llm"]
    tool_spans = [s for s in spans if s.span_kind == "tool"]
    eval_spans = [s for s in spans if s.span_kind == "evaluation"]
    human_spans = [s for s in spans if s.span_kind == "human"]
    
    # 1. Scaffolding Depth & Cognitive Complexity (Max: 25 pts)
    # Ratio of non-LLM scaffolding (orchestration, routing, multi-step execution) to direct LLM calls
    # A thin wrapper has ~1 LLM call per trace and 0-1 tools with no orchestration hierarchy
    llm_count = len(llm_spans)
    agent_count = len(agent_spans)
    tool_count = len(tool_spans)
    
    avg_spans_per_trace = total_spans / max(1, total_traces)
    avg_tools_per_trace = tool_count / max(1, total_traces)
    
    # Hierarchy check: spans with parent_span_id
    nested_spans = sum(1 for s in spans if s.parent_span_id is not None)
    hierarchy_ratio = nested_spans / max(1, total_spans)
    
    scaffolding_raw = (
        (min(avg_spans_per_trace / 5.0, 1.0) * 10.0) +
        (min(avg_tools_per_trace / 2.0, 1.0) * 8.0) +
        (hierarchy_ratio * 7.0)
    )
    scaffolding_score = round(min(scaffolding_raw, 25.0), 1)
    
    # 2. Model Sovereignty & Weight Ownership (Max: 25 pts)
    # Evaluates reliance on self-hosted / fine-tuned / open weights vs proprietary commercial APIs
    self_hosted_spans = sum(1 for s in llm_spans if s.gen_ai_system in ["self_hosted", "local", "vllm", "ollama", "tgi", "custom_finetuned"])
    total_llm_calls = max(1, len(llm_spans))
    self_hosted_ratio = self_hosted_spans / total_llm_calls
    
    # Multi-model orchestration bonus (not 100% reliant on a single external commercial model)
    unique_models = set(s.gen_ai_model for s in llm_spans if s.gen_ai_model)
    multi_model_bonus = 5.0 if len(unique_models) >= 3 else (2.5 if len(unique_models) == 2 else 0.0)
    
    sovereignty_raw = (self_hosted_ratio * 20.0) + multi_model_bonus
    sovereignty_score = round(min(sovereignty_raw, 25.0), 1)
    
    # 3. Custom Tool & Domain Integration Assets (Max: 25 pts)
    # Checks for domain tools, enterprise backends (CRM, vector search, custom endpoints)
    unique_tools = set(s.tool_name for s in tool_spans if s.tool_name)
    tool_count_val = len(unique_tools)
    
    # Custom enterprise connectors: tools that integrate internal knowledge or enterprise systems
    custom_connectors = [
        t for t in unique_tools 
        if any(kw in t.lower() for kw in ["crm", "erp", "internal", "vector", "rag", "sql", "db", "knowledge"])
    ]
    connector_ratio = len(custom_connectors) / max(1, tool_count_val) if tool_count_val > 0 else 0.0
    
    tool_raw = (
        (min(tool_count_val / 4.0, 1.0) * 12.0) +
        (connector_ratio * 13.0)
    )
    tool_score = round(min(tool_raw, 25.0), 1)
    
    # 4. Data Flywheel & Continuous Evaluation Loop (Max: 25 pts)
    # Checks presence of automated evaluation spans, guardrails, and human review feedback capture
    eval_coverage = len(eval_spans) / max(1, total_traces)
    human_feedback_captured = len(human_spans) > 0
    
    flywheel_raw = (
        (min(eval_coverage / 0.5, 1.0) * 18.0) +
        (7.0 if human_feedback_captured else 0.0)
    )
    flywheel_score = round(min(flywheel_raw, 25.0), 1)
    
    # Total Composite Moat Score (0 to 100)
    total_moat_score = round(scaffolding_score + sovereignty_score + tool_score + flywheel_score, 1)
    
    # Classification
    if total_moat_score >= 80.0:
        moat_class = "DEEP_DEFENSIBLE_MOAT"
        rep_months = 18.0
        rep_cost = 1750000
        summary = (
            "Deep proprietary moat. The target possesses custom model weights, multi-agent scaffolding, "
            "deep enterprise tool connectors, and an active evaluation flywheel that creates high switching costs."
        )
    elif total_moat_score >= 60.0:
        moat_class = "PROPRIETARY_COMPOUND_SYSTEM"
        rep_months = 10.0
        rep_cost = 850000
        summary = (
            "Proprietary compound AI architecture with moderate-to-high defensibility. Scaffolding, domain tool "
            "integrations, and evaluation systems exceed commodity wrappers, presenting tangible replication friction."
        )
    elif total_moat_score >= 35.0:
        moat_class = "LIGHT_SCAFFOLDING"
        rep_months = 4.5
        rep_cost = 320000
        summary = (
            "Light orchestration around third-party APIs. Limited proprietary weight IP or specialized domain tooling; "
            "defensibility is vulnerable to foundational model provider commoditization or native API advancements."
        )
    else:
        moat_class = "COMMODITY_WRAPPER"
        rep_months = 1.5
        rep_cost = 95000
        summary = (
            "High commodity risk. Architecture represents a thin wrapper directly calling off-the-shelf foundation models "
            "with negligible proprietary IP, zero weight sovereignty, and low switching barriers for competitors."
        )
        
    return {
        "moat_score": total_moat_score,
        "moat_classification": moat_class,
        "scaffolding_complexity_score": scaffolding_score,
        "weight_sovereignty_score": sovereignty_score,
        "tool_integration_score": tool_score,
        "data_flywheel_score": flywheel_score,
        "estimated_replication_months": rep_months,
        "estimated_replication_cost_usd": rep_cost,
        "breakdown": {
            "avg_spans_per_trace": round(avg_spans_per_trace, 2),
            "hierarchy_ratio_pct": round(hierarchy_ratio * 100, 1),
            "self_hosted_llm_ratio_pct": round(self_hosted_ratio * 100, 1),
            "unique_models_utilized": len(unique_models),
            "unique_tools_count": tool_count_val,
            "enterprise_connectors_count": len(custom_connectors),
            "evaluation_coverage_pct": round(eval_coverage * 100, 1),
            "feedback_loop_instrumented": human_feedback_captured
        },
        "verdict_summary": summary
    }
