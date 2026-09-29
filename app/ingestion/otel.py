import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple
from sqlalchemy.orm import Session

from app.db.models import Trace, Span, CostEvent, CostStatus, InterventionDetectionMethod
from app.config import settings

def parse_iso_datetime(dt_str: Any) -> datetime:
    if isinstance(dt_str, datetime):
        return dt_str
    if isinstance(dt_str, (int, float)):
        if dt_str > 1e11: # nanoseconds
            return datetime.fromtimestamp(dt_str / 1e9, tz=timezone.utc).replace(tzinfo=None)
        return datetime.fromtimestamp(dt_str, tz=timezone.utc).replace(tzinfo=None)
    if isinstance(dt_str, str):
        try:
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00')).replace(tzinfo=None)
        except Exception:
            return datetime.now(timezone.utc).replace(tzinfo=None)
    return datetime.now(timezone.utc).replace(tzinfo=None)

def compute_span_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> Tuple[float, CostStatus]:
    """
    Computes cost based on versioned model pricing.
    Returns (cost_usd, cost_status).
    If model pricing is unavailable, returns (0.0, CostStatus.UNKNOWN).
    """
    if not model:
        return 0.0, CostStatus.UNKNOWN
        
    model_lower = model.lower()
    provider_lower = (provider or "").lower()
    
    if "gpt-4o-mini" in model_lower:
        p_cost = settings.OPENAI_GPT4O_MINI_PROMPT_COST
        c_cost = settings.OPENAI_GPT4O_MINI_COMPLETION_COST
    elif "gpt-4o" in model_lower or "openai" in provider_lower:
        p_cost = settings.OPENAI_GPT4O_PROMPT_COST
        c_cost = settings.OPENAI_GPT4O_COMPLETION_COST
    elif "claude" in model_lower or "anthropic" in provider_lower:
        p_cost = settings.ANTHROPIC_CLAUDE_SONNET_PROMPT_COST
        c_cost = settings.ANTHROPIC_CLAUDE_SONNET_COMPLETION_COST
    elif "llama" in model_lower or "self_hosted" in provider_lower:
        p_cost = settings.LOCAL_LLAMA3_PROMPT_COST
        c_cost = settings.LOCAL_LLAMA3_COMPLETION_COST
    else:
        # Unknown unpriced model: DO NOT guess random price!
        return 0.0, CostStatus.UNKNOWN
        
    cost = (prompt_tokens / 1000.0 * p_cost) + (completion_tokens / 1000.0 * c_cost)
    return cost, CostStatus.MEASURED

def process_otlp_payload(db: Session, company_id: str, payload: Dict[str, Any]) -> Trace:
    """
    Parses OTLP trace payload with robust exception handling and explicit provenance tracking.
    """
    trace_id = payload.get("trace_id") or payload.get("traceId")
    spans_data = payload.get("spans", [])
    
    if not trace_id or not isinstance(spans_data, list) or len(spans_data) == 0:
        raise ValueError("Invalid OTLP payload: missing or malformed trace_id or spans list")
        
    # Calculate cryptographic SHA-256 provenance hash of the raw payload
    payload_str = json.dumps(payload, sort_keys=True, default=str)
    prov_hash = hashlib.sha256(payload_str.encode('utf-8')).hexdigest()
    
    start_times = []
    end_times = []
    
    for s in spans_data:
        try:
            start_times.append(parse_iso_datetime(s.get("start_time") or s.get("startTime")))
            end_times.append(parse_iso_datetime(s.get("end_time") or s.get("endTime")))
        except Exception:
            pass
            
    if not start_times:
        now_dt = datetime.now(timezone.utc).replace(tzinfo=None)
        start_times = [now_dt]
        end_times = [now_dt]
        
    trace_start = min(start_times)
    trace_end = max(end_times)
    duration_ms = max(0.0, (trace_end - trace_start).total_seconds() * 1000.0)
    
    trace_name = payload.get("name", spans_data[0].get("name", "agent_workflow") if spans_data else "agent_workflow")
    
    trace = Trace(
        id=trace_id,
        company_id=company_id,
        name=trace_name,
        start_time=trace_start,
        end_time=trace_end,
        duration_ms=duration_ms,
        status_code=payload.get("status_code", "OK"),
        has_human_intervention=False,
        total_cost=0.0,
        has_unpriced_model=False,
        provenance_hash=prov_hash
    )
    db.add(trace)
    
    total_trace_cost = 0.0
    has_human = False
    has_unpriced = False
    
    for s in spans_data:
        try:
            span_id = s.get("span_id") or s.get("spanId") or f"span_{len(trace.spans)}"
            attrs = s.get("attributes", {})
            if not isinstance(attrs, dict):
                attrs = {}
                
            gen_system = attrs.get("gen_ai.system") or attrs.get("gen_ai_system")
            gen_model = attrs.get("gen_ai.request.model") or attrs.get("gen_ai_model") or attrs.get("model")
            
            # Canonical OTel GenAI token count conventions
            try:
                prompt_tokens = int(
                    attrs.get("gen_ai.usage.input_tokens", 0) or 
                    attrs.get("gen_ai.usage.prompt_tokens", 0) or 
                    attrs.get("prompt_tokens", 0)
                )
            except Exception:
                prompt_tokens = 0
                
            try:
                comp_tokens = int(
                    attrs.get("gen_ai.usage.output_tokens", 0) or 
                    attrs.get("gen_ai.usage.completion_tokens", 0) or 
                    attrs.get("completion_tokens", 0)
                )
            except Exception:
                comp_tokens = 0
                
            span_kind = str(s.get("kind", s.get("span_kind", "agent"))).lower()
            span_name = str(s.get("name", "span")).lower()
            
            # Tool Identification
            tool_name = attrs.get("gen_ai.tool.name") or attrs.get("tool.name") or attrs.get("tool_name")
            if not tool_name and (span_kind == "tool" or "tool" in span_kind):
                tool_name = s.get("name", "unnamed_tool")
                
            # Error / Failure Identification
            is_error = False
            error_msg = None
            if (
                str(s.get("status_code", "")).upper() == "ERROR" or 
                attrs.get("error") or 
                s.get("error") or 
                "error" in attrs
            ):
                is_error = True
                error_msg = str(attrs.get("error.message") or attrs.get("error") or s.get("error") or "Execution failure")
            
            # Check human intervention method: EXPLICIT vs INFERRED
            is_human = False
            detection_method = InterventionDetectionMethod.OBSERVED_TELEMETRY
            
            if attrs.get("human_in_the_loop") or "human" in span_kind or "human" in span_name or "approval" in span_name or "override" in span_name:
                is_human = True
                detection_method = InterventionDetectionMethod.OBSERVED_TELEMETRY
            elif s.get("latency_gap_seconds", 0) > 300:
                is_human = True
                detection_method = InterventionDetectionMethod.INFERRED_HEURISTIC_LATENCY
                
            if is_human:
                has_human = True
                
            span_start = parse_iso_datetime(s.get("start_time") or s.get("startTime"))
            span_end = parse_iso_datetime(s.get("end_time") or s.get("endTime"))
            span_dur = max(0.0, (span_end - span_start).total_seconds() * 1000.0)
            
            span_cost = 0.0
            cost_status = CostStatus.MEASURED
            
            if gen_system or gen_model or prompt_tokens > 0:
                span_cost, cost_status = compute_span_cost(gen_system or "openai", gen_model or "gpt-4o", prompt_tokens, comp_tokens)
                if cost_status == CostStatus.UNKNOWN:
                    has_unpriced = True
                total_trace_cost += span_cost
                
                cost_cat = "evaluation" if ("eval" in span_name or "judge" in span_name or "guardrail" in span_name) else "inference"
                cost_event = CostEvent(
                    trace_id=trace_id,
                    span_id=span_id,
                    cost_category=cost_cat,
                    provider_name=gen_system or "unknown_provider",
                    model_name=gen_model or "unknown_model",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=comp_tokens,
                    cost_usd=span_cost,
                    cost_status=cost_status
                )
                db.add(cost_event)
            elif span_kind == "tool" or tool_name:
                # Tool invocation span
                pass
                
            span_obj = Span(
                id=span_id,
                trace_id=trace_id,
                parent_span_id=s.get("parent_span_id") or s.get("parentSpanId"),
                name=s.get("name", "span"),
                span_kind=span_kind,
                start_time=span_start,
                end_time=span_end,
                duration_ms=span_dur,
                gen_ai_system=gen_system,
                gen_ai_model=gen_model,
                gen_ai_prompt_tokens=prompt_tokens,
                gen_ai_completion_tokens=comp_tokens,
                tool_name=tool_name,
                is_error=is_error,
                error_message=error_msg,
                is_human_intervention=is_human,
                human_action_type=attrs.get("human_action_type"),
                detection_method=detection_method,
                cost=span_cost,
                cost_status=cost_status,
                attributes_json=attrs
            )
            db.add(span_obj)
            
        except Exception as span_err:
            # Continue parsing remaining spans safely
            continue
            
    trace.has_human_intervention = has_human
    trace.total_cost = total_trace_cost
    trace.has_unpriced_model = has_unpriced
    
    db.commit()
    return trace
