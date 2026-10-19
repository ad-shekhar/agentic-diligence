"""
Integration Tests for Real-Agent OpenTelemetry Trace Fixtures.
Validates end-to-end ingestion, normalization, token accounting, parent-child hierarchies,
and cryptographic provenance using sanitized real traces from LangGraph and Claude MCP.
"""

import os
import json
import hashlib
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.db.models import Company, Tenant, Trace, Span
from app.ingestion.otlp_handler import process_otlp_http_bytes, compute_raw_payload_hash
from app.ingestion.compatibility import INTEGRATION_MATRIX

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "real_traces")

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    tenant = Tenant(name="Real Trace Tenant")
    session.add(tenant)
    session.flush()
    company = Company(tenant_id=tenant.id, name="Real Agent Company")
    session.add(company)
    session.commit()
    yield session
    session.close()

def test_langgraph_openai_real_fixture(db_session):
    fixture_path = os.path.join(FIXTURES_DIR, "langchain_openai_real.json")
    assert os.path.exists(fixture_path), f"Fixture not found: {fixture_path}"

    with open(fixture_path, "rb") as f:
        raw_bytes = f.read()

    expected_hash = hashlib.sha256(raw_bytes).hexdigest()
    result = process_otlp_http_bytes(db_session, raw_bytes, content_type="application/json")

    assert result.status == "SUCCESS"
    assert result.payload_hash == expected_hash
    assert result.traces_count == 1
    assert result.spans_count == 4
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    assert trace_id in result.trace_ids

    # Inspect persisted trace in DB
    trace = db_session.query(Trace).filter(Trace.id == trace_id).first()
    assert trace is not None
    assert trace.provenance_hash == expected_hash
    assert len(trace.spans) == 4

    # Verify Root span
    root_span = db_session.query(Span).filter(Span.id == "00f067aa0ba902b7").first()
    assert root_span is not None
    assert root_span.parent_span_id == "" or root_span.parent_span_id is None
    assert root_span.name == "LangGraph_SupportOrchestrator"

    # Verify LLM generation span
    llm_span = db_session.query(Span).filter(Span.id == "5fb397be34d23b0f").first()
    assert llm_span is not None
    assert llm_span.parent_span_id == "00f067aa0ba902b7"
    assert llm_span.gen_ai_system == "openai"
    assert llm_span.gen_ai_model == "gpt-4o"
    assert llm_span.gen_ai_prompt_tokens == 540
    assert llm_span.gen_ai_completion_tokens == 135
    assert llm_span.cost > 0

    # Verify Tool execution span
    tool_span = db_session.query(Span).filter(Span.id == "321b8f10ea89bc72").first()
    assert tool_span is not None
    assert tool_span.tool_name == "postgres_order_lookup"

    # Verify Synthesis span
    synth_span = db_session.query(Span).filter(Span.id == "7aa99201bcde5431").first()
    assert synth_span is not None
    assert synth_span.gen_ai_model == "gpt-4o-mini"
    assert synth_span.gen_ai_prompt_tokens == 720
    assert synth_span.gen_ai_completion_tokens == 180

def test_claude_mcp_real_fixture(db_session):
    fixture_path = os.path.join(FIXTURES_DIR, "claude_mcp_real.json")
    assert os.path.exists(fixture_path), f"Fixture not found: {fixture_path}"

    with open(fixture_path, "rb") as f:
        raw_bytes = f.read()

    expected_hash = hashlib.sha256(raw_bytes).hexdigest()
    result = process_otlp_http_bytes(db_session, raw_bytes, content_type="application/json")

    assert result.status == "SUCCESS"
    assert result.payload_hash == expected_hash
    assert result.traces_count == 1
    assert result.spans_count == 2
    trace_id = "9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a"
    assert trace_id in result.trace_ids

    # Verify MCP tool execution span
    mcp_tool_span = db_session.query(Span).filter(Span.id == "1234567890abcdef").first()
    assert mcp_tool_span is not None
    assert mcp_tool_span.tool_name == "read_file"
    assert mcp_tool_span.gen_ai_system == "anthropic"

    # Verify Claude messages create span
    claude_span = db_session.query(Span).filter(Span.id == "fedcba0987654321").first()
    assert claude_span is not None
    assert claude_span.parent_span_id == "1234567890abcdef"
    assert claude_span.gen_ai_model == "claude-3-5-sonnet-20241022"
    assert claude_span.gen_ai_prompt_tokens == 1420
    assert claude_span.gen_ai_completion_tokens == 380

def test_compatibility_matrix_entries():
    assert "langchain_opentelemetry" in INTEGRATION_MATRIX
    assert "claude_mcp_observer" in INTEGRATION_MATRIX
    assert "crewai_opentelemetry" in INTEGRATION_MATRIX
    assert "standard_otlp_collector" in INTEGRATION_MATRIX

    mcp_entry = INTEGRATION_MATRIX["claude_mcp_observer"]
    assert mcp_entry.epistemic_level == "T2"
    assert "read_file" not in mcp_entry.unsupported_fields
