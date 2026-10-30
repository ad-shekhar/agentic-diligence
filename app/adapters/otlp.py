"""
OpenTelemetry (OTLP) Evidence Adapter (Phase 5).

Conforms to BaseEvidenceAdapter specification in docs/phase-5/evidence-adapter-architecture.md.
Acts as the canonical reference adapter for OTLP HTTP/JSON telemetry payloads.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from app.adapters.base import BaseEvidenceAdapter, AdapterCapability, ProvenanceEnvelope
from app.epistemic.tags import TrustLevel
from app.ingestion.schema import NormalizedSpan
from app.ingestion.normalizer import normalize_span_payload
from app.ingestion.otlp_handler import (
    MAX_PAYLOAD_SIZE_BYTES,
    IngestionError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
    extract_spans_from_otlp_envelope,
    compute_raw_payload_hash,
    validate_trace_span_id,
)


class OtlpEvidenceAdapter(BaseEvidenceAdapter):
    """
    Standard OpenTelemetry HTTP/JSON Evidence Adapter.
    Normalizes OTel GenAI semantic convention spans into the canonical evidence schema.
    """
    adapter_id: str = "otlp_evidence_adapter"
    adapter_version: str = "1.28.0"
    source_framework: str = "opentelemetry"
    source_version: str = "v1.28.0"
    default_trust_level: TrustLevel = TrustLevel.T1

    def declared_capabilities(self) -> List[AdapterCapability]:
        """Observational capabilities supported by OpenTelemetry GenAI conventions."""
        return [
            AdapterCapability.CAN_OBSERVE_TOOL_CALL,
            AdapterCapability.CAN_OBSERVE_TOOL_EXECUTION_RESULT,
            AdapterCapability.CAN_OBSERVE_HUMAN_INTERVENTION,
            AdapterCapability.CAN_OBSERVE_TOKEN_USAGE,
            AdapterCapability.CAN_OBSERVE_COST,
            AdapterCapability.CAN_OBSERVE_MODEL_IDENTITY,
            AdapterCapability.CAN_OBSERVE_SERVER_SIDE_ERRORS,
        ]

    def known_blind_spots(self) -> List[str]:
        """Formal disclosure of unobservable telemetry regions."""
        return [
            "Uninstrumented out-of-band human intervention outside OpenTelemetry tracer context",
            "Internal model reasoning thoughts when unexported by provider SDK",
            "Downstream non-HTTP tool execution environments (e.g. uninstrumented OS subprocesses)",
            "Client-side UI render latency and client dropouts prior to span dispatch",
        ]

    def validate_payload(self, raw_bytes: bytes, content_type: str = "application/json") -> Dict[str, Any]:
        """
        Enforces 10 MB payload boundaries, media type restrictions, and JSON syntax.
        Returns deserialized JSON dict on success.
        """
        byte_size = len(raw_bytes)
        if byte_size > MAX_PAYLOAD_SIZE_BYTES:
            raise PayloadTooLargeError(f"Payload size {byte_size} bytes exceeds 10 MB limit.")

        ct_clean = content_type.split(";")[0].strip().lower()
        if ct_clean in ["application/x-protobuf", "application/protobuf"]:
            raise UnsupportedMediaTypeError(
                "Unsupported Content-Type: Protobuf format is deferred. Please export as OTLP HTTP/JSON."
            )

        if ct_clean not in ["application/json", "application/x-json", "text/json", ""]:
            raise UnsupportedMediaTypeError(
                f"Unsupported Content-Type: {content_type}. Expected 'application/json'."
            )

        try:
            payload = json.loads(raw_bytes.decode("utf-8"))
        except Exception as json_err:
            raise IngestionError(f"Malformed JSON payload: {str(json_err)}")

        if not isinstance(payload, dict):
            raise IngestionError("Invalid JSON root: OTLP request must be a JSON object.")

        return payload

    def parse_and_normalize(
        self,
        raw_bytes: bytes,
        content_type: str = "application/json",
        company_id: Optional[str] = None,
        provenance_hash: Optional[str] = None
    ) -> Tuple[ProvenanceEnvelope, List[NormalizedSpan]]:
        """
        Parses OTLP HTTP/JSON request, normalizes spans to v1.28.0 conventions,
        and constructs the cryptographic ProvenanceEnvelope.
        """
        payload = self.validate_payload(raw_bytes, content_type)
        payload_hash = provenance_hash or compute_raw_payload_hash(raw_bytes)

        extracted = extract_spans_from_otlp_envelope(payload)
        if not extracted:
            raise IngestionError("No valid spans found in payload.")

        normalized_spans: List[NormalizedSpan] = []
        errors: List[str] = []

        for raw_span, default_tid, r_attrs in extracted:
            try:
                tid_candidate = raw_span.get("traceId") or raw_span.get("trace_id") or default_tid
                tid = validate_trace_span_id(tid_candidate, "traceId")
                sid_candidate = raw_span.get("spanId") or raw_span.get("span_id")
                validate_trace_span_id(sid_candidate, "spanId")

                # If resource attributes exist, attach them into raw_span attributes under resource prefix if not set
                if r_attrs and isinstance(raw_span.get("attributes"), dict):
                    for r_k, r_v in r_attrs.items():
                        if r_k not in raw_span["attributes"]:
                            raw_span["attributes"][f"resource.{r_k}"] = r_v

                span = normalize_span_payload(
                    raw_span=raw_span,
                    default_trace_id=tid,
                    trust_level=self.default_trust_level,
                )
                span.raw_attributes["provenance_hash"] = payload_hash
                normalized_spans.append(span)
            except Exception as e:
                errors.append(str(e))

        if not normalized_spans:
            raise IngestionError(f"All spans failed normalization: {'; '.join(errors)}")

        envelope = self.create_provenance_envelope(
            raw_bytes=raw_bytes,
            content_type=content_type,
            provenance_hash=payload_hash,
            custom_metadata={
                "company_id": company_id,
                "total_spans": len(normalized_spans),
                "unique_traces": len({s.trace_id for s in normalized_spans}),
            },
        )

        return envelope, normalized_spans