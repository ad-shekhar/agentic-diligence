"""
Unit and Integration Tests for OTLP HTTP/JSON Ingestion Layer.
Validates protocol handling, input validation, content-type checks,
payload size boundaries, and SHA-256 provenance calculation.
"""

import hashlib
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.db.session import Base
from app.db.models import Company, Tenant, Trace, PayloadProvenance
from app.main import app
from app.ingestion.otlp_handler import (
    process_otlp_http_bytes,
    compute_raw_payload_hash,
    IngestionError,
    UnsupportedMediaTypeError,
    PayloadTooLargeError
)

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    tenant = Tenant(name="Ingest Test Tenant")
    session.add(tenant)
    session.flush()
    company = Company(tenant_id=tenant.id, name="Ingest Test Company")
    session.add(company)
    session.commit()
    yield session
    session.close()

def test_raw_payload_hash_reproducibility():
    raw_data = b'{"resourceSpans": []}'
    expected = hashlib.sha256(raw_data).hexdigest()
    assert compute_raw_payload_hash(raw_data) == expected

def test_ingest_valid_standard_resource_spans(db_session):
    company = db_session.query(Company).first()
    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "test_agent"}}]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "trace1234567890abcdef1234567890ab",
                                "spanId": "span1234567890ab",
                                "name": "agent_llm_step",
                                "kind": 3,
                                "startTimeUnixNano": "1726999200000000000",
                                "endTimeUnixNano": "1726999201000000000",
                                "attributes": [
                                    {"key": "gen_ai.provider.name", "value": {"stringValue": "openai"}},
                                    {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}},
                                    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": 500}},
                                    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 100}}
                                ],
                                "status": {"code": 1}
                            }
                        ]
                    }
                ]
            }
        ]
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    expected_hash = hashlib.sha256(raw_bytes).hexdigest()

    result = process_otlp_http_bytes(
        db_session,
        raw_bytes,
        content_type="application/json",
        company_id=company.id
    )

    assert result.status == "SUCCESS"
    assert result.payload_hash == expected_hash
    assert result.traces_count == 1
    assert result.spans_count == 1
    assert "trace1234567890abcdef1234567890ab" in result.trace_ids

    # Verify database persistence
    db_trace = db_session.query(Trace).filter(Trace.id == "trace1234567890abcdef1234567890ab").first()
    assert db_trace is not None
    assert db_trace.provenance_hash == expected_hash
    assert len(db_trace.spans) == 1
    assert db_trace.total_cost > 0

    # Verify PayloadProvenance record
    prov = db_session.query(PayloadProvenance).filter(PayloadProvenance.payload_hash == expected_hash).first()
    assert prov is not None
    assert prov.status == "SUCCESS"
    assert prov.span_count == 1

def test_ingest_simplified_spans_payload(db_session):
    company = db_session.query(Company).first()
    payload = {
        "trace_id": "simple_trace_999",
        "spans": [
            {
                "span_id": "simple_span_1",
                "name": "chat_step",
                "kind": "llm",
                "attributes": {
                    "gen_ai.system": "anthropic",
                    "model": "claude-3-5-sonnet",
                    "prompt_tokens": 800,
                    "completion_tokens": 200
                }
            }
        ]
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    result = process_otlp_http_bytes(db_session, raw_bytes, company_id=company.id)
    assert result.status == "SUCCESS"
    assert result.traces_count == 1

def test_ingest_unsupported_content_type(db_session):
    raw_bytes = b"\x08\x01\x12\x04test"
    with pytest.raises(UnsupportedMediaTypeError) as exc_info:
        process_otlp_http_bytes(db_session, raw_bytes, content_type="application/x-protobuf")
    assert "Protobuf format is deferred" in str(exc_info.value)

def test_ingest_malformed_json(db_session):
    bad_bytes = b"{{invalid_json_format"
    with pytest.raises(IngestionError) as exc_info:
        process_otlp_http_bytes(db_session, bad_bytes, content_type="application/json")
    assert "Malformed JSON" in str(exc_info.value)

def test_ingest_empty_spans(db_session):
    empty_payload = json.dumps({"resourceSpans": []}).encode("utf-8")
    with pytest.raises(IngestionError) as exc_info:
        process_otlp_http_bytes(db_session, empty_payload)
    assert "empty" in str(exc_info.value).lower()

def test_ingest_oversized_payload():
    large_bytes = b"x" * (11 * 1024 * 1024) # 11 MB > 10 MB limit
    with pytest.raises(PayloadTooLargeError) as exc_info:
        process_otlp_http_bytes(None, large_bytes)
    assert "exceeds 10 MB limit" in str(exc_info.value)

def test_ingest_invalid_trace_or_span_id(db_session):
    payload = {
        "spans": [
            {
                "trace_id": "", # Invalid empty trace ID
                "span_id": "span_1",
                "name": "bad_trace_id"
            }
        ]
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    with pytest.raises(IngestionError) as exc_info:
        process_otlp_http_bytes(db_session, raw_bytes)
    assert "Invalid traceId" in str(exc_info.value)

def test_fastapi_v1_traces_endpoint():
    with TestClient(app) as client:
        payload = {
            "trace_id": "fastapi_test_trace_1",
            "spans": [
                {
                    "span_id": "fastapi_span_1",
                    "name": "fastapi_span",
                    "attributes": {
                        "gen_ai.provider.name": "openai",
                        "gen_ai.request.model": "gpt-4o",
                        "gen_ai.usage.input_tokens": 100,
                        "gen_ai.usage.output_tokens": 25
                    }
                }
            ]
        }
        response = client.post(
            "/v1/traces",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SUCCESS"
        assert "payload_hash" in data
        assert data["spans_count"] == 1

def test_fastapi_v1_compatibility_endpoint():
    with TestClient(app) as client:
        response = client.get("/v1/compatibility")
        assert response.status_code == 200
        matrix = response.json()
        assert "langchain_opentelemetry" in matrix
        assert "claude_mcp_observer" in matrix
        assert "standard_otlp_collector" in matrix

