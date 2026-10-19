"""
OTLP HTTP/JSON Ingestion Handler.
Processes incoming OpenTelemetry trace exports, computes cryptographic SHA-256
payload provenance, normalizes spans, and stores audit-grade telemetry records.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.ingestion.schema import NormalizedSpan, NormalizedTrace, IngestionResult, NormalizationVersion
from app.ingestion.normalizer import normalize_span_payload, flatten_otlp_attributes
from app.db.models import Trace, Span, CostEvent, CostStatus, InterventionDetectionMethod, PayloadProvenance, Company

MAX_PAYLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB maximum payload size

HEX_ID_PATTERN = re.compile(r"^[0-9a-fA-F]+$")

class IngestionError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

class UnsupportedMediaTypeError(IngestionError):
    def __init__(self, message: str = "Unsupported Media Type: Only 'application/json' is currently supported for OTLP HTTP ingestion. Protobuf binary ingestion is deferred."):
        super().__init__(message, status_code=415)

class PayloadTooLargeError(IngestionError):
    def __init__(self, message: str = "Payload Too Large: Maximum allowed batch size is 10 MB."):
        super().__init__(message, status_code=413)

def compute_raw_payload_hash(raw_bytes: bytes) -> str:
    """
    Computes canonical SHA-256 digest of exact raw incoming request bytes before parsing.
    """
    return hashlib.sha256(raw_bytes).hexdigest()

def validate_trace_span_id(identifier: Optional[str], id_type: str = "trace_id") -> str:
    """
    Validates traceId or spanId.
    Must be a non-empty string.
    """
    if not identifier or not isinstance(identifier, str) or len(identifier.strip()) == 0:
        raise IngestionError(f"Invalid {id_type}: identifier must be a non-empty string.")
    return identifier.strip()

def extract_spans_from_otlp_envelope(payload: Dict[str, Any]) -> List[Tuple[Dict[str, Any], Optional[str], Optional[Dict[str, Any]]]]:
    """
    Extracts raw span dictionaries from either standard OTLP envelope
    (resourceSpans -> scopeSpans -> spans) or simplified trace payload ({trace_id: ..., spans: [...]}).
    Returns list of tuples: (raw_span, default_trace_id, resource_attributes).
    """
    extracted_spans = []

    # 1. Standard OTLP HTTP/JSON format
    if "resourceSpans" in payload:
        resource_spans = payload.get("resourceSpans")
        if not isinstance(resource_spans, list):
            raise IngestionError("Malformed OTLP payload: 'resourceSpans' must be a list.")
        if len(resource_spans) == 0:
            raise IngestionError("Empty OTLP payload: 'resourceSpans' list is empty.")

        for r_span in resource_spans:
            if not isinstance(r_span, dict):
                continue
            r_attrs = flatten_otlp_attributes(r_span.get("resource", {}).get("attributes", {}))
            scope_spans = r_span.get("scopeSpans", [])
            if not isinstance(scope_spans, list):
                continue
            for s_span in scope_spans:
                if not isinstance(s_span, dict):
                    continue
                spans_list = s_span.get("spans", [])
                if not isinstance(spans_list, list):
                    continue
                for span in spans_list:
                    if isinstance(span, dict):
                        extracted_spans.append((span, None, r_attrs))

    # 2. Simplified format ({trace_id: ..., spans: [...]})
    elif "spans" in payload:
        spans_list = payload.get("spans")
        if not isinstance(spans_list, list):
            raise IngestionError("Malformed payload: 'spans' must be a list.")
        if len(spans_list) == 0:
            raise IngestionError("Empty payload: 'spans' list is empty.")
        top_trace_id = payload.get("trace_id") or payload.get("traceId")
        for span in spans_list:
            if isinstance(span, dict):
                extracted_spans.append((span, top_trace_id, {}))

    else:
        raise IngestionError("Unrecognized OTLP request structure: missing 'resourceSpans' or 'spans'.")

    return extracted_spans

def process_otlp_http_bytes(
    db: Optional[Session],
    raw_bytes: bytes,
    content_type: str = "application/json",
    company_id: Optional[str] = None
) -> IngestionResult:
    """
    Ingests and normalizes an OTLP HTTP request from exact raw bytes.
    Enforces payload size limits, validates content-type, computes SHA-256 provenance,
    normalizes spans with GenAI conventions, and records provenance in database.
    """
    import time
    start_time = time.time()

    # 1. Size Validation
    byte_size = len(raw_bytes)
    if byte_size > MAX_PAYLOAD_SIZE_BYTES:
        raise PayloadTooLargeError(f"Payload size {byte_size} bytes exceeds 10 MB limit.")

    # 2. Compute Raw Provenance Hash
    payload_hash = compute_raw_payload_hash(raw_bytes)

    # 3. Content-Type Validation
    ct_clean = content_type.split(";")[0].strip().lower()
    if ct_clean in ["application/x-protobuf", "application/protobuf"]:
        # Record failed provenance before raising
        if db:
            prov = PayloadProvenance(
                payload_hash=payload_hash,
                company_id=company_id,
                content_type=content_type,
                byte_size=byte_size,
                format="otlp_protobuf",
                status="FAILED",
                error_message="Protobuf binary ingestion is deferred."
            )
            db.add(prov)
            db.commit()
        raise UnsupportedMediaTypeError("Unsupported Content-Type: Protobuf format is deferred. Please export as OTLP HTTP/JSON.")

    if ct_clean not in ["application/json", "application/x-json", "text/json", ""]:
        if db:
            prov = PayloadProvenance(
                payload_hash=payload_hash,
                company_id=company_id,
                content_type=content_type,
                byte_size=byte_size,
                status="FAILED",
                error_message=f"Unsupported content type: {content_type}"
            )
            db.add(prov)
            db.commit()
        raise UnsupportedMediaTypeError(f"Unsupported Content-Type: {content_type}. Expected 'application/json'.")

    # 4. JSON Deserialization
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except Exception as json_err:
        if db:
            prov = PayloadProvenance(
                payload_hash=payload_hash,
                company_id=company_id,
                content_type=content_type,
                byte_size=byte_size,
                status="FAILED",
                error_message=f"Invalid JSON: {str(json_err)}"
            )
            db.add(prov)
            db.commit()
        raise IngestionError(f"Malformed JSON payload: {str(json_err)}")

    if not isinstance(payload, dict):
        raise IngestionError("Invalid JSON root: OTLP request must be a JSON object.")

    # 5. Extract Spans
    try:
        extracted = extract_spans_from_otlp_envelope(payload)
    except IngestionError as env_err:
        if db:
            prov = PayloadProvenance(
                payload_hash=payload_hash,
                company_id=company_id,
                content_type=content_type,
                byte_size=byte_size,
                status="FAILED",
                error_message=str(env_err)
            )
            db.add(prov)
            db.commit()
        raise env_err

    if not extracted:
        raise IngestionError("No valid spans found in payload.")

    # 6. Normalize Spans & Group by Trace ID
    trace_groups: Dict[str, List[NormalizedSpan]] = {}
    errors: List[str] = []

    for raw_span, default_tid, r_attrs in extracted:
        try:
            tid_candidate = raw_span.get("traceId") or raw_span.get("trace_id") or default_tid
            tid = validate_trace_span_id(tid_candidate, "traceId")
            sid_candidate = raw_span.get("spanId") or raw_span.get("span_id")
            sid = validate_trace_span_id(sid_candidate, "spanId")

            normalized = normalize_span_payload(raw_span, default_trace_id=tid)
            if tid not in trace_groups:
                trace_groups[tid] = []
            trace_groups[tid].append(normalized)
        except Exception as span_err:
            errors.append(f"Failed to normalize span: {str(span_err)}")

    if not trace_groups:
        raise IngestionError(f"All spans failed normalization: {'; '.join(errors)}")

    # 7. Persist to Database if session provided
    spans_count = sum(len(spans) for spans in trace_groups.values())
    if db:
        # Resolve company_id if not explicitly provided
        effective_company_id = company_id
        if not effective_company_id:
            first_company = db.query(Company).first()
            if first_company:
                effective_company_id = first_company.id

        for tid, n_spans in trace_groups.items():
            start_times = [s.start_time for s in n_spans]
            end_times = [s.end_time for s in n_spans]
            trace_start = min(start_times) if start_times else datetime.now(timezone.utc).replace(tzinfo=None)
            trace_end = max(end_times) if end_times else trace_start
            duration_ms = max(0.0, (trace_end - trace_start).total_seconds() * 1000.0)

            total_cost = sum(s.cost_usd for s in n_spans)
            has_human = any(s.is_human_intervention for s in n_spans)
            has_unpriced = any(s.cost_status == "UNKNOWN" for s in n_spans)

            # Check if trace exists (idempotent / duplicate submission handling)
            existing_trace = db.query(Trace).filter(Trace.id == tid).first()
            if existing_trace:
                # Update provenance hash and total cost if updated
                existing_trace.provenance_hash = payload_hash
                existing_trace.total_cost = total_cost
                trace_obj = existing_trace
            else:
                trace_obj = Trace(
                    id=tid,
                    company_id=effective_company_id or "default_target",
                    name=n_spans[0].name if n_spans else "agent_workflow",
                    start_time=trace_start,
                    end_time=trace_end,
                    duration_ms=duration_ms,
                    status_code="OK",
                    has_human_intervention=has_human,
                    total_cost=total_cost,
                    has_unpriced_model=has_unpriced,
                    provenance_hash=payload_hash
                )
                db.add(trace_obj)

            for s in n_spans:
                existing_span = db.query(Span).filter(Span.id == s.span_id).first()
                if not existing_span:
                    det_method = InterventionDetectionMethod.OBSERVED_TELEMETRY
                    if s.intervention_detection_method == "INFERRED_HEURISTIC_LATENCY":
                        det_method = InterventionDetectionMethod.INFERRED_HEURISTIC_LATENCY

                    c_status = CostStatus.MEASURED
                    if s.cost_status == "UNKNOWN":
                        c_status = CostStatus.UNKNOWN

                    span_obj = Span(
                        id=s.span_id,
                        trace_id=tid,
                        parent_span_id=s.parent_span_id,
                        name=s.name,
                        span_kind=s.span_kind,
                        start_time=s.start_time,
                        end_time=s.end_time,
                        duration_ms=s.duration_ms,
                        gen_ai_system=s.provider_name,
                        gen_ai_model=s.requested_model or s.response_model,
                        gen_ai_prompt_tokens=s.input_tokens or 0,
                        gen_ai_completion_tokens=s.output_tokens or 0,
                        tool_name=s.tool_name,
                        is_error=(s.status_code == "ERROR"),
                        error_message=s.status_message,
                        is_human_intervention=s.is_human_intervention,
                        human_action_type=s.human_action_type,
                        detection_method=det_method,
                        cost=s.cost_usd,
                        cost_status=c_status,
                        attributes_json=s.raw_attributes
                    )
                    db.add(span_obj)

                    if s.has_token_data and s.cost_usd > 0:
                        cost_cat = "evaluation" if ("eval" in s.name.lower() or "judge" in s.name.lower()) else "inference"
                        cost_event = CostEvent(
                            trace_id=tid,
                            span_id=s.span_id,
                            cost_category=cost_cat,
                            provider_name=s.provider_name or "unknown",
                            model_name=s.requested_model or "unknown",
                            prompt_tokens=s.input_tokens or 0,
                            completion_tokens=s.output_tokens or 0,
                            cost_usd=s.cost_usd,
                            cost_status=c_status
                        )
                        db.add(cost_event)

        # Record Payload Provenance
        prov_record = PayloadProvenance(
            payload_hash=payload_hash,
            company_id=effective_company_id,
            content_type=content_type,
            byte_size=byte_size,
            format="otlp_http_json",
            normalization_version=NormalizationVersion.V1_28_0.value,
            trace_count=len(trace_groups),
            span_count=spans_count,
            status="SUCCESS" if not errors else "PARTIAL",
            error_message="; ".join(errors) if errors else None
        )
        db.add(prov_record)
        db.commit()

    duration_ms = (time.time() - start_time) * 1000.0

    return IngestionResult(
        status="SUCCESS" if not errors else "PARTIAL",
        payload_hash=payload_hash,
        byte_size=byte_size,
        content_type=content_type,
        normalization_version=NormalizationVersion.V1_28_0.value,
        traces_count=len(trace_groups),
        spans_count=spans_count,
        trace_ids=list(trace_groups.keys()),
        errors=errors,
        duration_ms=duration_ms
    )
