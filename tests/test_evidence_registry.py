"""
Phase 6 Milestone A Tests: Unified Evidence Registry.

Validates multi-source evidence registration, auto-detection,
deterministic evidence IDs, duplicate detection, and provenance tracking.
"""

import hashlib
import json
import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.db.models import Company, Tenant, PayloadProvenance
from app.adapters.registry import (
    SourceType,
    EvidenceStatus,
    UnifiedEvidenceRegistry,
    compute_deterministic_evidence_id,
)
from app.epistemic.tags import EpistemicTag, TrustLevel


@pytest.fixture
def registry():
    reg = UnifiedEvidenceRegistry()
    reg.clear()
    return reg


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    tenant = Tenant(name="Registry Tenant")
    session.add(tenant)
    session.flush()
    company = Company(tenant_id=tenant.id, name="Target Company Alpha")
    session.add(company)
    session.commit()
    yield session
    session.close()


# ==============================================================================
# 1. Source Type Auto-Detection Tests
# ==============================================================================

def test_source_type_auto_detection(registry):
    """Registry accurately detects OTLP, MCP, and Browser payloads."""
    otlp_payload = json.dumps({"resourceSpans": [{"resource": {}, "scopeSpans": []}]}).encode("utf-8")
    mcp_payload = json.dumps({"messages": [{"jsonrpc": "2.0", "id": 1, "method": "tools/call"}]}).encode("utf-8")
    browser_payload = json.dumps({"actions": [{"action_type": "click", "target_selector": "button"}]}).encode("utf-8")

    assert registry.detect_source_type(otlp_payload) == SourceType.OTLP
    assert registry.detect_source_type(mcp_payload) == SourceType.MCP
    assert registry.detect_source_type(browser_payload) == SourceType.BROWSER

    # Explicit hint override
    assert registry.detect_source_type(otlp_payload, hint="mcp") == SourceType.MCP


# ==============================================================================
# 2. Multi-Source Ingestion & Deterministic Provenance
# ==============================================================================

def test_unified_registry_ingestion_and_provenance(registry):
    """Registry ingests OTLP, MCP, and Browser evidence, preserving provenance."""
    # 1. OTLP Span
    otlp_bytes = json.dumps({
        "spans": [
            {
                "trace_id": "trace-reg-001",
                "span_id": "span-reg-001",
                "name": "agent_plan",
                "start_time_ns": 1729000000000000000,
                "end_time_ns": 1729000000500000000,
                "attributes": {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.usage.prompt_tokens": 100,
                    "gen_ai.usage.completion_tokens": 50,
                }
            }
        ]
    }).encode("utf-8")

    r_otlp = registry.register_payload(otlp_bytes, company_id="comp-001")
    assert r_otlp.status == "SUCCESS"
    assert r_otlp.source_type == SourceType.OTLP
    assert r_otlp.total_spans_ingested == 1
    assert r_otlp.payload_hash == hashlib.sha256(otlp_bytes).hexdigest()

    # 2. MCP JSON-RPC
    mcp_bytes = json.dumps({
        "trace_id": "trace-reg-001",
        "messages": [
            {
                "jsonrpc": "2.0",
                "id": "mcp-call-01",
                "method": "tools/call",
                "params": {"name": "calculate_tax", "arguments": {}}
            },
            {
                "jsonrpc": "2.0",
                "id": "mcp-call-01",
                "result": {"content": [{"type": "text", "text": "0.08"}], "isError": False}
            }
        ]
    }).encode("utf-8")

    r_mcp = registry.register_payload(mcp_bytes, company_id="comp-001")
    assert r_mcp.status == "SUCCESS"
    assert r_mcp.source_type == SourceType.MCP
    assert r_mcp.total_spans_ingested == 1

    # 3. Browser Action
    browser_bytes = json.dumps({
        "trace_id": "trace-reg-001",
        "actions": [
            {
                "action_type": "approval_modal_confirm",
                "action_id": "modal-01",
                "target_selector": "button#approve",
                "duration_ms": 120.0
            }
        ]
    }).encode("utf-8")

    r_browser = registry.register_payload(browser_bytes, company_id="comp-001")
    assert r_browser.status == "SUCCESS"
    assert r_browser.source_type == SourceType.BROWSER
    assert r_browser.total_spans_ingested == 1

    # Query registry by trace
    records = registry.get_records(trace_id="trace-reg-001")
    assert len(records) == 3

    source_types = [r.source_type for r in records]
    assert SourceType.OTLP in source_types
    assert SourceType.MCP in source_types
    assert SourceType.BROWSER in source_types


def test_deterministic_evidence_id_calculation():
    """Evidence IDs are deterministic, unique, and strictly repeatable."""
    eid1 = compute_deterministic_evidence_id("otlp", "hash_abc", "trace_1", "span_1")
    eid2 = compute_deterministic_evidence_id("otlp", "hash_abc", "trace_1", "span_1")
    eid3 = compute_deterministic_evidence_id("mcp", "hash_abc", "trace_1", "span_1")

    assert eid1 == eid2
    assert len(eid1) == 64
    assert eid1 != eid3  # Different source type produces different evidence ID


# ==============================================================================
# 3. Deduplication & Idempotency Tests
# ==============================================================================

def test_registry_deduplication(registry):
    """Registering identical payload twice marks subsequent spans as DUPLICATE without data loss."""
    payload = json.dumps({
        "spans": [
            {
                "trace_id": "trace-dedup-01",
                "span_id": "span-dedup-01",
                "name": "dedup_task",
                "start_time_ns": 1729000000000000000,
                "end_time_ns": 1729000000100000000,
                "attributes": {}
            }
        ]
    }).encode("utf-8")

    r1 = registry.register_payload(payload, company_id="comp-dedup")
    assert r1.duplicates_detected == 0

    r2 = registry.register_payload(payload, company_id="comp-dedup")
    assert r2.duplicates_detected == 1

    # Default query excludes duplicates
    clean_records = registry.get_records(company_id="comp-dedup", include_duplicates=False)
    assert len(clean_records) == 1
    assert clean_records[0].status == EvidenceStatus.VALID

    # Explicit query includes duplicates
    all_records = registry.get_records(company_id="comp-dedup", include_duplicates=True)
    assert len(all_records) == 2
    statuses = [r.status for r in all_records]
    assert EvidenceStatus.VALID in statuses
    assert EvidenceStatus.DUPLICATE in statuses


# ==============================================================================
# 4. Incomplete / Unknown Evidence Tracking
# ==============================================================================

def test_registry_incomplete_evidence_status(registry):
    """Unanswered MCP tool request is explicitly marked with EvidenceStatus.INCOMPLETE."""
    payload = json.dumps({
        "messages": [
            {
                "jsonrpc": "2.0",
                "id": "unanswered-99",
                "method": "tools/call",
                "params": {"name": "hung_task"}
            }
        ]
    }).encode("utf-8")

    receipt = registry.register_payload(payload, company_id="comp-hung")
    assert receipt.status == "SUCCESS"

    records = registry.get_records(company_id="comp-hung")
    assert len(records) == 1
    assert records[0].status == EvidenceStatus.INCOMPLETE
    assert records[0].epistemic_tag == EpistemicTag.UNKNOWN
    assert records[0].span.tool_status == "UNKNOWN"


# ==============================================================================
# 5. SQLite Persistence Integration
# ==============================================================================

def test_registry_database_provenance_persistence(registry, db_session):
    """When DB session is supplied, PayloadProvenance record is saved to SQLite."""
    payload = json.dumps({
        "spans": [
            {
                "trace_id": "trace-db-01",
                "span_id": "span-db-01",
                "name": "db_task",
                "attributes": {}
            }
        ]
    }).encode("utf-8")

    receipt = registry.register_payload(payload, company_id="Target Company Alpha", db=db_session)
    assert receipt.status == "SUCCESS"

    prov = db_session.query(PayloadProvenance).filter(
        PayloadProvenance.payload_hash == receipt.payload_hash
    ).first()

    assert prov is not None
    assert prov.payload_hash == hashlib.sha256(payload).hexdigest()
    assert prov.byte_size == len(payload)
    assert prov.status == "SUCCESS"

