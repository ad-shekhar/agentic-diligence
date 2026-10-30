"""
Phase 5 Unit Tests: Evidence Adapter Contracts & OTLP Reference Implementation.

Validates the BaseEvidenceAdapter interface, ProvenanceEnvelope canonicalization,
and OtlpEvidenceAdapter compliance according to docs/phase-5/evidence-adapter-architecture.md.
"""

import hashlib
import json
import pytest
from datetime import datetime, timezone

from app.adapters.base import (
    AdapterCapability,
    ProvenanceEnvelope,
    BaseEvidenceAdapter,
)
from app.adapters.otlp import OtlpEvidenceAdapter
from app.epistemic.tags import TrustLevel
from app.ingestion.otlp_handler import (
    IngestionError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)


# ==============================================================================
# 1. ProvenanceEnvelope Unit Tests
# ==============================================================================

def test_provenance_envelope_serialization():
    """ProvenanceEnvelope converts to dictionary and canonical JSON with sorted keys."""
    now = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)
    envelope = ProvenanceEnvelope(
        adapter_id="test_adapter",
        adapter_version="1.0.0",
        source_framework="langchain",
        source_version="0.2.6",
        payload_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        byte_size=1024,
        content_type="application/json",
        ingested_at_utc=now,
        epistemic_trust_level=TrustLevel.T1,
        capabilities=[
            AdapterCapability.CAN_OBSERVE_TOOL_CALL,
            AdapterCapability.CAN_OBSERVE_TOKEN_USAGE,
        ],
        known_blind_spots=["Out-of-band human edits"],
        redacted_fields=["api_key"],
        custom_metadata={"test_run": True},
    )

    d = envelope.to_dict()
    assert d["adapter_id"] == "test_adapter"
    assert d["epistemic_trust_level"] == "T1"
    assert "can_observe_tool_call" in d["capabilities"]
    assert "can_observe_token_usage" in d["capabilities"]
    assert d["known_blind_spots"] == ["Out-of-band human edits"]
    assert d["redacted_fields"] == ["api_key"]
    assert d["custom_metadata"]["test_run"] is True

    # Canonical JSON checks
    canonical_compact = envelope.to_canonical_json(pretty=False)
    canonical_pretty = envelope.to_canonical_json(pretty=True)

    # Must be valid JSON
    parsed = json.loads(canonical_compact)
    assert parsed["adapter_id"] == "test_adapter"

    # Keys must be alphabetically sorted
    keys = list(parsed.keys())
    assert keys == sorted(keys)

    # Hash computation
    digest = envelope.compute_envelope_hash()
    assert len(digest) == 64
    assert digest == hashlib.sha256(canonical_compact.encode("utf-8")).hexdigest()


# ==============================================================================
# 2. BaseEvidenceAdapter Abstract Interface Tests
# ==============================================================================

def test_base_adapter_abstract_instantiation():
    """BaseEvidenceAdapter cannot be instantiated directly without abstract methods."""
    class IncompleteAdapter(BaseEvidenceAdapter):
        pass

    with pytest.raises(TypeError):
        IncompleteAdapter()  # type: ignore


def test_base_adapter_helper_methods():
    """Concrete subclass inherits helper methods for hashing and envelope creation."""
    class DummyAdapter(BaseEvidenceAdapter):
        adapter_id = "dummy"
        adapter_version = "0.1.0"
        source_framework = "mock"
        source_version = "0.0.1"
        default_trust_level = TrustLevel.T2

        def declared_capabilities(self):
            return [AdapterCapability.CAN_OBSERVE_COST]

        def known_blind_spots(self):
            return ["Everything else"]

        def validate_payload(self, raw_bytes: bytes, content_type: str):
            pass

        def parse_and_normalize(self, raw_bytes: bytes, content_type: str = "application/json", company_id=None, provenance_hash=None):
            env = self.create_provenance_envelope(raw_bytes, content_type, provenance_hash)
            return env, []

    adapter = DummyAdapter()
    raw = b'{"hello": "world"}'
    expected_hash = hashlib.sha256(raw) .hexdigest()
    assert adapter.compute_sha256(raw) == expected_hash

    env, spans = adapter.parse_and_normalize(raw)
    assert env.adapter_id == "dummy"
    assert env.epistemic_trust_level == TrustLevel.T2
    assert env.payload_sha256 == expected_hash
    assert env.byte_size == len(raw)
    assert spans == []


# ==============================================================================
# 3. OtlpEvidenceAdapter Compliance Tests
# ==============================================================================

@pytest.fixture
def otlp_adapter():
    return OtlpEvidenceAdapter()


def test_otlp_adapter_metadata_and_capabilities(otlp_adapter):
    """OtlpEvidenceAdapter declares expected OTel GenAI capabilities and blind spots."""
    assert otlp_adapter.adapter_id == "otlp_evidence_adapter"
    assert otlp_adapter.adapter_version == "1.28.0"
    assert otlp_adapter.source_framework == "opentelemetry"
    assert otlp_adapter.default_trust_level == TrustLevel.T1

    caps = otlp_adapter.declared_capabilities()
    assert AdapterCapability.CAN_OBSERVE_TOOL_CALL in caps
    assert AdapterCapability.CAN_OBSERVE_TOOL_EXECUTION_RESULT in caps
    assert AdapterCapability.CAN_OBSERVE_HUMAN_INTERVENTION in caps
    assert AdapterCapability.CAN_OBSERVE_TOKEN_USAGE in caps
    assert AdapterCapability.CAN_OBSERVE_COST in caps
    assert AdapterCapability.CAN_OBSERVE_MODEL_IDENTITY in caps
    assert AdapterCapability.CAN_OBSERVE_SERVER_SIDE_ERRORS in caps

    blind_spots = otlp_adapter.known_blind_spots()
    assert len(blind_spots) >= 3
    assert any("out-of-band human" in s.lower() for s in blind_spots)


def test_otlp_adapter_size_limit_enforcement(otlp_adapter):
    """Payloads exceeding 10 MB are rejected with PayloadTooLargeError (413)."""
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    with pytest.raises(PayloadTooLargeError) as exc_info:
        otlp_adapter.validate_payload(oversized, "application/json")
    assert exc_info.value.status_code == 413


def test_otlp_adapter_media_type_validation(otlp_adapter):
    """Protobuf binary and non-JSON media types are rejected with UnsupportedMediaTypeError (415)."""
    valid_json = b'{"resourceSpans": []}'

    # Protobuf binary deferred
    with pytest.raises(UnsupportedMediaTypeError) as exc1:
        otlp_adapter.validate_payload(valid_json, "application/x-protobuf")
    assert exc1.value.status_code == 415

    # Other media types
    with pytest.raises(UnsupportedMediaTypeError) as exc2:
        otlp_adapter.validate_payload(valid_json, "text/xml")
    assert exc2.value.status_code == 415


def test_otlp_adapter_malformed_json_rejection(otlp_adapter):
    """Malformed JSON syntax is rejected with IngestionError (400)."""
    with pytest.raises(IngestionError) as exc:
        otlp_adapter.validate_payload(b"{bad-json", "application/json")
    assert exc.value.status_code == 400


def test_otlp_adapter_non_dict_json_rejection(otlp_adapter):
    """JSON that is not a dictionary root is rejected with IngestionError (400)."""
    with pytest.raises(IngestionError) as exc:
        otlp_adapter.validate_payload(b"[1, 2, 3]", "application/json")
    assert "must be a JSON object" in str(exc.value)


def test_otlp_adapter_parse_and_normalize_standard_envelope(otlp_adapter):
    """Standard resourceSpans payload normalizes spans and produces complete ProvenanceEnvelope."""
    payload_dict = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "payment-agent"}}
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "11112222333344445555666677778888",
                                "spanId": "aaaabbbbccccdddd",
                                "name": "chat_openai_generate",
                                "kind": 3,
                                "startTimeUnixNano": "1729000000000000000",
                                "endTimeUnixNano": "1729000001500000000",
                                "attributes": [
                                    {"key": "gen_ai.system", "value": {"stringValue": "openai"}},
                                    {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}},
                                    {"key": "gen_ai.usage.prompt_tokens", "value": {"intValue": 150}},
                                    {"key": "gen_ai.usage.completion_tokens", "value": {"intValue": 45}},
                                ],
                                "status": {"code": 1}
                            }
                        ]
                    }
                ]
            }
        ]
    }
    raw_bytes = json.dumps(payload_dict).encode("utf-8")
    expected_hash = hashlib.sha256(raw_bytes).hexdigest()

    envelope, spans = otlp_adapter.parse_and_normalize(
        raw_bytes=raw_bytes,
        content_type="application/json",
        company_id="acme-target"
    )

    assert envelope.adapter_id == "otlp_evidence_adapter"
    assert envelope.payload_sha256 == expected_hash
    assert envelope.byte_size == len(raw_bytes)
    assert envelope.epistemic_trust_level == TrustLevel.T1
    assert envelope.custom_metadata["company_id"] == "acme-target"
    assert envelope.custom_metadata["total_spans"] == 1

    assert len(spans) == 1
    span = spans[0]
    assert span.trace_id == "11112222333344445555666677778888"
    assert span.span_id == "aaaabbbbccccdddd"
    assert span.provider_name == "openai"
    assert span.requested_model == "gpt-4o"
    assert span.input_tokens == 150
    assert span.output_tokens == 45
    assert span.has_token_data is True
    assert span.raw_attributes["provenance_hash"] == expected_hash


def test_otlp_adapter_zero_token_preservation(otlp_adapter):
    """Zero token count (0) is explicitly preserved and distinct from missing tokens (None)."""
    payload_dict = {
        "spans": [
            {
                "trace_id": "trace-zero-tokens",
                "span_id": "span-zero-tokens",
                "name": "cached_query",
                "start_time_ns": 1729000000000000000,
                "end_time_ns": 1729000000100000000,
                "attributes": {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o-mini",
                    "gen_ai.usage.prompt_tokens": 0,
                    "gen_ai.usage.completion_tokens": 0,
                }
            },
            {
                "trace_id": "trace-none-tokens",
                "span_id": "span-none-tokens",
                "name": "unmetered_tool",
                "start_time_ns": 1729000000200000000,
                "end_time_ns": 1729000000300000000,
                "attributes": {
                    "tool.name": "local_calculator"
                }
            }
        ]
    }
    raw_bytes = json.dumps(payload_dict).encode("utf-8")

    envelope, spans = otlp_adapter.parse_and_normalize(raw_bytes)
    assert len(spans) == 2

    # Span 1: 0 tokens explicitly preserved
    assert spans[0].input_tokens == 0
    assert spans[0].output_tokens == 0
    assert spans[0].has_token_data is True

    # Span 2: None tokens preserved without coercing to 0
    assert spans[1].input_tokens is None
    assert spans[1].output_tokens is None
    assert spans[1].has_token_data is False
