"""
Versioned Semantic Normalizer for OpenTelemetry GenAI Telemetry.
Complies with OpenTelemetry GenAI Semantic Conventions v1.28.0 while providing
documented legacy alias compatibility, deterministic conflict resolution,
and explicit missing-field tracking.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Union
from app.ingestion.schema import NormalizedSpan, NormalizationVersion
from app.epistemic.tags import EpistemicTag, TrustLevel
from app.ingestion.otel import compute_span_cost

# Pinned Semantic Convention Specification
SUPPORTED_CONVENTION_VERSION = "OpenTelemetry GenAI Semantic Conventions v1.28.0"

# Attribute Aliases Registry (Ordered by precedence: highest precedence first)
PROVIDER_ALIASES = [
    ("gen_ai.provider.name", "v1.28.0"),
    ("gen_ai.system", "v1.26.0_legacy"),
    ("llm.provider", "framework_alias"),
    ("ai.system", "framework_alias"),
    ("model.provider", "framework_alias"),
]

REQUEST_MODEL_ALIASES = [
    ("gen_ai.request.model", "v1.28.0"),
    ("llm.model", "framework_alias"),
    ("model_name", "framework_alias"),
    ("openai.model", "framework_alias"),
    ("model", "generic_alias")
]

RESPONSE_MODEL_ALIASES = [
    ("gen_ai.response.model", "v1.28.0"),
    ("gen_ai.model", "v1.26.0_legacy"),
    ("response_model", "framework_alias")
]

INPUT_TOKEN_ALIASES = [
    ("gen_ai.usage.input_tokens", "v1.28.0"),
    ("gen_ai.usage.prompt_tokens", "v1.26.0_legacy"),
    ("prompt_tokens", "framework_alias"),
    ("llm.tokens.prompt", "framework_alias"),
    ("tokens.prompt", "framework_alias")
]

OUTPUT_TOKEN_ALIASES = [
    ("gen_ai.usage.output_tokens", "v1.28.0"),
    ("gen_ai.usage.completion_tokens", "v1.26.0_legacy"),
    ("completion_tokens", "framework_alias"),
    ("llm.tokens.completion", "framework_alias"),
    ("tokens.completion", "framework_alias")
]

OPERATION_NAME_ALIASES = [
    ("gen_ai.operation.name", "v1.28.0"),
    ("llm.operation", "framework_alias"),
    ("operation.name", "generic_alias"),
    ("span.type", "generic_alias")
]

TOOL_NAME_ALIASES = [
    ("gen_ai.tool.name", "v1.28.0"),
    ("tool.name", "framework_alias"),
    ("tool_name", "framework_alias")
]

KNOWN_GENAI_ATTRIBUTES = {
    key for alias_list in [
        PROVIDER_ALIASES, REQUEST_MODEL_ALIASES, RESPONSE_MODEL_ALIASES,
        INPUT_TOKEN_ALIASES, OUTPUT_TOKEN_ALIASES, OPERATION_NAME_ALIASES,
        TOOL_NAME_ALIASES
    ] for key, _ in alias_list
} | {
    "error", "error.message", "human_in_the_loop", "human_action_type",
    "latency_gap_seconds", "gen_ai.tool.call_id", "gen_ai.tool.status",
    "gen_ai.prompt", "gen_ai.completion"
}

def extract_otlp_attribute_value(val: Any) -> Any:
    """
    Extracts scalar or complex value from OTLP AnyValue Protobuf-JSON dictionary or native type.
    """
    if isinstance(val, dict):
        if "stringValue" in val:
            return val["stringValue"]
        if "intValue" in val:
            try:
                return int(val["intValue"])
            except (ValueError, TypeError):
                return val["intValue"]
        if "doubleValue" in val:
            try:
                return float(val["doubleValue"])
            except (ValueError, TypeError):
                return val["doubleValue"]
        if "boolValue" in val:
            return bool(val["boolValue"])
        if "arrayValue" in val:
            values = val["arrayValue"].get("values", [])
            return [extract_otlp_attribute_value(v) for v in values]
        if "kvlistValue" in val:
            values = val["kvlistValue"].get("values", [])
            return {item.get("key"): extract_otlp_attribute_value(item.get("value")) for item in values}
    return val

def flatten_otlp_attributes(raw_attrs: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalizes both OTLP key-value lists and flattened dictionaries into standard Python dict.
    """
    if isinstance(raw_attrs, list):
        flattened = {}
        for item in raw_attrs:
            if isinstance(item, dict) and "key" in item:
                k = item["key"]
                v = extract_otlp_attribute_value(item.get("value"))
                flattened[k] = v
        return flattened
    elif isinstance(raw_attrs, dict):
        return {k: extract_otlp_attribute_value(v) for k, v in raw_attrs.items()}
    return {}

def parse_otlp_timestamp(ts: Any) -> datetime:
    """
    Parses unix nano, unix sec, or ISO timestamp into timezone-naive UTC datetime.
    """
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=None)
    if isinstance(ts, (int, float)):
        if ts > 1e11:  # Nanoseconds
            return datetime.fromtimestamp(ts / 1e9, tz=timezone.utc).replace(tzinfo=None)
        return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
    if isinstance(ts, str):
        if ts.isdigit():
            val = int(ts)
            if val > 1e11:
                return datetime.fromtimestamp(val / 1e9, tz=timezone.utc).replace(tzinfo=None)
            return datetime.fromtimestamp(val, tz=timezone.utc).replace(tzinfo=None)
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return datetime.now(timezone.utc).replace(tzinfo=None)
    return datetime.now(timezone.utc).replace(tzinfo=None)

def resolve_aliased_attribute(
    attrs: Dict[str, Any],
    alias_list: List[Tuple[str, str]]
) -> Tuple[Optional[Any], Optional[str], Optional[Dict[str, Any]]]:
    """
    Deterministically resolves an attribute across prioritized aliases.
    If multiple aliases are present with differing values, selects the highest precedence
    and records the conflict.
    """
    selected_val = None
    selected_key = None
    conflict_data = None

    present_values = []
    for key, spec_origin in alias_list:
        if key in attrs and attrs[key] is not None:
            present_values.append((key, attrs[key], spec_origin))

    if not present_values:
        return None, None, None

    # Highest precedence is first in alias_list
    selected_key, selected_val, _ = present_values[0]

    # Detect conflicts if multiple aliases have different non-empty values
    if len(present_values) > 1:
        primary_val_str = str(selected_val).strip().lower()
        for other_key, other_val, _ in present_values[1:]:
            if str(other_val).strip().lower() != primary_val_str:
                conflict_data = {
                    "selected": selected_val,
                    "selected_key": selected_key,
                    "conflicting": other_val,
                    "conflicting_key": other_key
                }
                break

    return selected_val, selected_key, conflict_data

def normalize_span_payload(
    raw_span: Dict[str, Any],
    default_trace_id: Optional[str] = None,
    trust_level: TrustLevel = TrustLevel.T1
) -> NormalizedSpan:
    """
    Converts a single raw OTel span dictionary into canonical NormalizedSpan.
    Extracts timestamps, status, GenAI conventions, token usage, tool metadata,
    conflicts, and unmapped attributes.
    """
    span_id = str(raw_span.get("spanId") or raw_span.get("span_id") or "unspecified_span_id")
    trace_id = str(raw_span.get("traceId") or raw_span.get("trace_id") or default_trace_id or "unspecified_trace_id")
    parent_span_id = raw_span.get("parentSpanId") or raw_span.get("parent_span_id")
    name = str(raw_span.get("name") or "unnamed_span")
    span_kind = str(raw_span.get("kind") or raw_span.get("span_kind") or "INTERNAL")

    # Timestamps & Duration
    start_ts = (
        raw_span.get("startTimeUnixNano")
        or raw_span.get("start_time")
        or raw_span.get("startTime")
        or raw_span.get("start_time_ns")
        or raw_span.get("start_time_unix_nano")
    )
    end_ts = (
        raw_span.get("endTimeUnixNano")
        or raw_span.get("end_time")
        or raw_span.get("endTime")
        or raw_span.get("end_time_ns")
        or raw_span.get("end_time_unix_nano")
    )

    # Use fixed sentinel (Unix epoch) when timestamp is absent to keep normalization deterministic.
    # Callers can detect missing timestamps by checking duration_ms == 0 and missing_fields.
    _EPOCH_SENTINEL = datetime(1970, 1, 1, 0, 0, 0)
    start_dt = parse_otlp_timestamp(start_ts) if start_ts is not None else _EPOCH_SENTINEL
    end_dt = parse_otlp_timestamp(end_ts) if end_ts is not None else start_dt
    duration_ms = max(0.0, (end_dt - start_dt).total_seconds() * 1000.0)

    # Status Code
    status_raw = raw_span.get("status", {})
    status_code = "UNSET"
    status_msg = None
    if isinstance(status_raw, dict):
        code_val = status_raw.get("code")
        status_msg = status_raw.get("message")
        if code_val == 1 or code_val == "OK" or code_val == "STATUS_CODE_OK":
            status_code = "OK"
        elif code_val == 2 or code_val == "ERROR" or code_val == "STATUS_CODE_ERROR":
            status_code = "ERROR"
    elif isinstance(status_raw, str):
        status_code = status_raw.upper()

    # Flatten Attributes
    raw_attrs = raw_span.get("attributes", {})
    attrs = flatten_otlp_attributes(raw_attrs)

    conflicts: Dict[str, Dict[str, Any]] = {}
    missing_fields: List[str] = []

    # 1. Resolve Provider
    provider_name, prov_key, prov_conf = resolve_aliased_attribute(attrs, PROVIDER_ALIASES)
    if prov_conf:
        conflicts["provider_name"] = prov_conf
    if provider_name is None:
        missing_fields.append("provider_name")

    # 2. Resolve Request Model
    req_model, req_key, req_conf = resolve_aliased_attribute(attrs, REQUEST_MODEL_ALIASES)
    if req_conf:
        conflicts["requested_model"] = req_conf
    if req_model is None:
        missing_fields.append("requested_model")

    # 3. Resolve Response Model
    resp_model, resp_key, resp_conf = resolve_aliased_attribute(attrs, RESPONSE_MODEL_ALIASES)
    if resp_conf:
        conflicts["response_model"] = resp_conf

    # 4. Resolve Operation Name
    op_name, op_key, op_conf = resolve_aliased_attribute(attrs, OPERATION_NAME_ALIASES)
    if op_conf:
        conflicts["operation_name"] = op_conf

    # 5. Token Usage: Explicit distinction between 0 and None
    in_tokens_raw, in_key, in_conf = resolve_aliased_attribute(attrs, INPUT_TOKEN_ALIASES)
    if in_conf:
        conflicts["input_tokens"] = in_conf
    input_tokens = None
    if in_tokens_raw is not None:
        try:
            input_tokens = int(in_tokens_raw)
        except (ValueError, TypeError):
            input_tokens = None
    else:
        missing_fields.append("input_tokens")

    out_tokens_raw, out_key, out_conf = resolve_aliased_attribute(attrs, OUTPUT_TOKEN_ALIASES)
    if out_conf:
        conflicts["output_tokens"] = out_conf
    output_tokens = None
    if out_tokens_raw is not None:
        try:
            output_tokens = int(out_tokens_raw)
        except (ValueError, TypeError):
            output_tokens = None
    else:
        missing_fields.append("output_tokens")

    has_token_data = (input_tokens is not None or output_tokens is not None)

    # 6. Tool Metadata
    tool_name, tool_key, tool_conf = resolve_aliased_attribute(attrs, TOOL_NAME_ALIASES)
    if tool_conf:
        conflicts["tool_name"] = tool_conf
    tool_call_id = attrs.get("gen_ai.tool.call_id") or attrs.get("gen_ai.tool.call.id") or attrs.get("tool_call_id") or attrs.get("tool.call_id")
    tool_status = attrs.get("gen_ai.tool.status")

    # 7. Error Detection
    if attrs.get("error") or attrs.get("error.message"):
        status_code = "ERROR"
        status_msg = str(attrs.get("error.message") or attrs.get("error"))

    # 8. Human Intervention Detection
    is_human = False
    hitl_method = None
    hitl_type = attrs.get("human_action_type")
    if attrs.get("human_in_the_loop") or "human" in name.lower() or "approval" in name.lower():
        is_human = True
        hitl_method = "OBSERVED_TELEMETRY"
    elif attrs.get("latency_gap_seconds", 0) > 300:
        is_human = True
        hitl_method = "INFERRED_HEURISTIC_LATENCY"

    # 9. Cost Computation
    effective_model = req_model or resp_model or "unknown"
    effective_provider = provider_name or "unknown"
    p_tokens = input_tokens if input_tokens is not None else 0
    c_tokens = output_tokens if output_tokens is not None else 0
    cost_usd, cost_status = compute_span_cost(effective_provider, effective_model, p_tokens, c_tokens)

    # 10. Preserve Unmapped Attributes
    unmapped = {k: v for k, v in attrs.items() if k not in KNOWN_GENAI_ATTRIBUTES}

    return NormalizedSpan(
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        name=name,
        span_kind=span_kind,
        start_time=start_dt,
        end_time=end_dt,
        duration_ms=duration_ms,
        status_code=status_code,
        status_message=status_msg,
        provider_name=provider_name,
        requested_model=req_model,
        response_model=resp_model,
        operation_name=op_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        has_token_data=has_token_data,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_status=tool_status,
        is_human_intervention=is_human,
        human_action_type=hitl_type,
        intervention_detection_method=hitl_method,
        cost_usd=cost_usd,
        cost_status=cost_status.value if hasattr(cost_status, "value") else str(cost_status),
        epistemic_tag=EpistemicTag.OBSERVED,
        trust_level=trust_level,
        normalization_version=NormalizationVersion.V1_28_0.value,
        unmapped_attributes=unmapped,
        conflicts=conflicts,
        missing_fields=missing_fields,
        raw_attributes=attrs
    )
