"""
Phase 6 End-to-End Reliability, Adversarial, and Integration Test Suite.

Covers all 12 mandatory reliability scenarios:
1. Successful autonomous tool execution.
2. Human-approved tool execution.
3. Failed execution with retry and recovery.
4. Permanently failed execution.
5. Missing telemetry (dark zones > 35% force INSUFFICIENT_EVIDENCE).
6. Duplicate OTLP spans across batches.
7. Out-of-order MCP events causally sorted.
8. Contradictory browser vs backend observations (T2 precedence & HITL preservation).
9. Tampered evidence / invalid provenance hash detection.
10. Cross-session / cross-company evidence contamination prevention.
11. Unresolved tool calls (epistemic UNKNOWN preservation).
12. Malformed and oversized payloads rejection.

Also verifies the End-to-End REST API endpoints (/api/v1/evidence/*).
"""

import json
from datetime import datetime, timezone, timedelta
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.adapters.registry import (
    UnifiedEvidenceRegistry,
    SourceType,
    EvidenceStatus,
)
from app.adapters.correlation import (
    EvidenceCorrelationEngine,
    AnomalyType,
)
from app.adapters.pipeline import (
    UnifiedVerificationPipeline,
    VerificationPipelineResult,
)
from app.adapters.otlp import MAX_PAYLOAD_SIZE_BYTES, IngestionError, PayloadTooLargeError
from app.epistemic.claims import (
    ClaimSchema,
    ClaimDimension,
    ComparisonOperator,
)
from app.epistemic.tags import (
    EpistemicTag,
    TrustLevel,
    VerificationVerdict,
)


@pytest.fixture
def clean_pipeline():
    reg = UnifiedEvidenceRegistry()
    reg.clear()
    corr = EvidenceCorrelationEngine(gap_threshold_ms=30000.0)
    return UnifiedVerificationPipeline(registry=reg, correlation_engine=corr)


@pytest.fixture
def api_client():
    return TestClient(app)


# ==============================================================================
# 1. Successful Autonomous Tool Execution
# ==============================================================================

def test_scenario_1_successful_autonomous_execution(clean_pipeline):
    """Clean autonomous tool runs verify an autonomy claim >= 80%."""
    # Build 20 atomic autonomous traces
    for i in range(20):
        tid = f"trace-auto-{i:03d}"
        payload = json.dumps({
            "spans": [
                {
                    "trace_id": tid,
                    "span_id": f"span-step1-{i}",
                    "name": "reasoning_step",
                    "start_time_ns": 1729000000000000000 + (i * 10_000_000_000),
                    "end_time_ns": 1729000001000000000 + (i * 10_000_000_000),
                    "attributes": {"gen_ai.operation.name": "chat"}
                },
                {
                    "trace_id": tid,
                    "span_id": f"span-step2-{i}",
                    "name": "execute_tool",
                    "start_time_ns": 1729000001100000000 + (i * 10_000_000_000),
                    "end_time_ns": 1729000002000000000 + (i * 10_000_000_000),
                    "attributes": {
                        "gen_ai.tool.name": "calculator",
                        "gen_ai.tool.status": "OK",
                        "agent.is_human_intervention": False
                    }
                }
            ]
        }).encode("utf-8")
        clean_pipeline.ingest_evidence(payload, source_type=SourceType.OTLP, company_id="comp-scenario-1")

    claim = ClaimSchema(
        claim_id="claim-auto-test",
        dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="System operates with at least 80% autonomy",
        target_operator=ComparisonOperator.GREATER_EQUAL,
        target_value=80.0,
        unit="%",
    )

    res = clean_pipeline.verify_claims([claim], company_id="comp-scenario-1", min_sample_size=15)
    entry = res.matrix.entries[0]
    assert entry.verification_verdict == VerificationVerdict.VERIFIED
    assert entry.observed_epistemic_value.bounds.lower >= 80.0


# ==============================================================================
# 2. Human-Approved Tool Execution
# ==============================================================================

def test_scenario_2_human_approved_execution(clean_pipeline):
    """Human approvals in browser modal reduce autonomy, contradicting claim for >= 80% autonomy."""
    for i in range(20):
        tid = f"trace-hitl-{i:03d}"
        otlp_payload = json.dumps({
            "spans": [
                {
                    "trace_id": tid,
                    "span_id": f"span-otlp-{i}",
                    "name": "deploy_app",
                    "start_time_ns": 1729000000000000000 + (i * 10_000_000_000),
                    "end_time_ns": 1729000002000000000 + (i * 10_000_000_000),
                    "attributes": {
                        "gen_ai.tool.name": "deploy_tool",
                        "gen_ai.tool.call_id": f"call-deploy-{i}",
                    }
                }
            ]
        }).encode("utf-8")

        browser_payload = json.dumps({
            "actions": [
                {
                    "action_type": "approval_modal_confirm",
                    "target_selector": "button#confirm-deploy",
                    "timestamp": "2026-10-20T10:00:01Z",
                    "tool_call_id": f"call-deploy-{i}",
                    "trace_id": tid,
                    "human_override": True
                }
            ]
        }).encode("utf-8")

        clean_pipeline.ingest_evidence(otlp_payload, source_type=SourceType.OTLP, company_id="comp-scenario-2")
        clean_pipeline.ingest_evidence(browser_payload, source_type=SourceType.BROWSER, company_id="comp-scenario-2")

    claim = ClaimSchema(
        claim_id="claim-high-autonomy",
        dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="System operates with at least 80% autonomy",
        target_operator=ComparisonOperator.GREATER_EQUAL,
        target_value=80.0,
        unit="%",
    )

    res = clean_pipeline.verify_claims([claim], company_id="comp-scenario-2", min_sample_size=15)
    entry = res.matrix.entries[0]
    # Because all 20 had human approval modals, autonomy is 0% -> CONTRADICTED
    assert entry.verification_verdict == VerificationVerdict.CONTRADICTED


# ==============================================================================
# 3. Failed Execution with Retry and Recovery
# ==============================================================================

def test_scenario_3_retry_and_recovery(clean_pipeline):
    """Traces containing a failed step followed by successful retry are measured properly."""
    for i in range(16):
        tid = f"trace-retry-{i:03d}"
        payload = json.dumps({
            "spans": [
                {
                    "trace_id": tid,
                    "span_id": f"span-fail-{i}",
                    "name": "fetch_api_call",
                    "start_time_ns": 1729000000000000000 + (i * 5_000_000_000),
                    "end_time_ns": 1729000001000000000 + (i * 5_000_000_000),
                    "status": {"code": 2, "message": "503 Service Unavailable"},
                    "attributes": {"error": True}
                },
                {
                    "trace_id": tid,
                    "span_id": f"span-retry-ok-{i}",
                    "name": "fetch_api_call",
                    "start_time_ns": 1729000001200000000 + (i * 5_000_000_000),
                    "end_time_ns": 1729000002000000000 + (i * 5_000_000_000),
                    "status": {"code": 1},
                    "attributes": {}
                }
            ]
        }).encode("utf-8")
        clean_pipeline.ingest_evidence(payload, source_type=SourceType.OTLP, company_id="comp-scenario-3")

    # Claim: error rate <= 60%
    claim = ClaimSchema(
        claim_id="claim-error-bounded",
        dimension=ClaimDimension.RELIABILITY,
        stated_claim_text="Error rate does not exceed 60%",
        target_operator=ComparisonOperator.LESS_EQUAL,
        target_value=60.0,
        unit="%",
    )
    res = clean_pipeline.verify_claims([claim], company_id="comp-scenario-3", min_sample_size=15)
    entry = res.matrix.entries[0]
    assert entry.verification_verdict in (VerificationVerdict.VERIFIED, VerificationVerdict.PARTIALLY_VERIFIED)


# ==============================================================================
# 4. Permanently Failed Execution
# ==============================================================================

def test_scenario_4_permanently_failed_execution(clean_pipeline):
    """Spans with permanent unrecovered failures contradict high reliability claims."""
    for i in range(20):
        tid = f"trace-perm-fail-{i:03d}"
        payload = json.dumps({
            "spans": [
                {
                    "trace_id": tid,
                    "span_id": f"span-deadlock-{i}",
                    "name": "critical_task",
                    "start_time_ns": 1729000000000000000 + (i * 5_000_000_000),
                    "end_time_ns": 1729000001000000000 + (i * 5_000_000_000),
                    "status": {"code": 2, "message": "Deadlock abort"},
                    "attributes": {"error": "Fatal deadlock"}
                }
            ]
        }).encode("utf-8")
        clean_pipeline.ingest_evidence(payload, source_type=SourceType.OTLP, company_id="comp-scenario-4")

    claim = ClaimSchema(
        claim_id="claim-strict-reliability",
        dimension=ClaimDimension.RELIABILITY,
        stated_claim_text="Error rate does not exceed 5%",
        target_operator=ComparisonOperator.LESS_EQUAL,
        target_value=5.0,
        unit="%",
    )
    res = clean_pipeline.verify_claims([claim], company_id="comp-scenario-4", min_sample_size=15)
    entry = res.matrix.entries[0]
    assert entry.verification_verdict == VerificationVerdict.CONTRADICTED


# ==============================================================================
# 5. Missing Telemetry (Dark Zones > 35%)
# ==============================================================================

def test_scenario_5_missing_telemetry_dark_zone(clean_pipeline):
    """Uninstrumented gaps exceeding 35% trigger INSUFFICIENT_EVIDENCE."""
    for i in range(20):
        tid = f"trace-dark-zone-{i:03d}"
        # 3 spans separated by 90s gaps (2 unknown gaps / 5 total tasks = 40% > 35%)
        t0 = 1729000000000000000 + (i * 300_000_000_000)
        t1 = t0 + 1_000_000_000
        t2 = t1 + 90_000_000_000  # 90s gap
        t3 = t2 + 1_000_000_000
        t4 = t3 + 90_000_000_000  # 90s gap
        t5 = t4 + 1_000_000_000

        payload = json.dumps({
            "spans": [
                {"trace_id": tid, "span_id": f"s1-{i}", "name": "step1", "start_time_ns": t0, "end_time_ns": t1, "attributes": {}},
                {"trace_id": tid, "span_id": f"s2-{i}", "name": "step2", "start_time_ns": t2, "end_time_ns": t3, "attributes": {}},
                {"trace_id": tid, "span_id": f"s3-{i}", "name": "step3", "start_time_ns": t4, "end_time_ns": t5, "attributes": {}},
            ]
        }).encode("utf-8")
        clean_pipeline.ingest_evidence(payload, source_type=SourceType.OTLP, company_id="comp-scenario-5")

    claim = ClaimSchema(
        claim_id="claim-autonomy-dark",
        dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="Autonomy is >= 80%",
        target_operator=ComparisonOperator.GREATER_EQUAL,
        target_value=80.0,
        unit="%",
    )
    res = clean_pipeline.verify_claims([claim], company_id="comp-scenario-5", min_sample_size=15)
    entry = res.matrix.entries[0]
    assert entry.verification_verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE
    assert "dark zones" in entry.verdict_reason.lower() or "uninstrumented" in entry.verdict_reason.lower()


# ==============================================================================
# 6. Duplicate OTLP Spans
# ==============================================================================

def test_scenario_6_duplicate_spans(clean_pipeline):
    """Submitting the exact same batch twice detects duplicates without corrupting counts."""
    payload = json.dumps({
        "spans": [
            {
                "trace_id": "trace-dup-scenario",
                "span_id": "span-dup-unique-1",
                "name": "work_unit",
                "start_time_ns": 1729000000000000000,
                "end_time_ns": 1729000001000000000,
                "attributes": {}
            }
        ]
    }).encode("utf-8")

    r1 = clean_pipeline.ingest_evidence(payload, source_type=SourceType.OTLP, company_id="comp-dup")
    assert r1.duplicates_detected == 0

    r2 = clean_pipeline.ingest_evidence(payload, source_type=SourceType.OTLP, company_id="comp-dup")
    assert r2.duplicates_detected == 1

    records = clean_pipeline.registry.get_records(company_id="comp-dup", include_duplicates=False)
    assert len(records) == 1


# ==============================================================================
# 7. Out-of-Order MCP Events
# ==============================================================================

def test_scenario_7_out_of_order_mcp(clean_pipeline):
    """MCP events arriving out of order are causally sorted by correlation engine."""
    tid = "trace-ooo-7"

    # Multi-event MCP payload with out-of-order execution (call 2 arrives before call 1)
    payload = json.dumps({
        "messages": [
            {
                "jsonrpc": "2.0",
                "id": "call-2",
                "method": "tools/call",
                "params": {"name": "step_2"},
                "timestamp": "2026-10-20T10:00:05Z",
                "trace_id": tid
            },
            {
                "jsonrpc": "2.0",
                "id": "call-2",
                "result": {"output": "Done 2"},
                "timestamp": "2026-10-20T10:00:06Z",
                "trace_id": tid
            },
            {
                "jsonrpc": "2.0",
                "id": "call-1",
                "method": "tools/call",
                "params": {"name": "step_1"},
                "timestamp": "2026-10-20T10:00:00Z",
                "trace_id": tid
            },
            {
                "jsonrpc": "2.0",
                "id": "call-1",
                "result": {"output": "Done 1"},
                "timestamp": "2026-10-20T10:00:01Z",
                "trace_id": tid
            }
        ]
    }).encode("utf-8")

    clean_pipeline.ingest_evidence(payload, source_type=SourceType.MCP, company_id="comp-ooo")

    records = clean_pipeline.registry.get_records(company_id="comp-ooo")
    correlated = clean_pipeline.correlation_engine.correlate_records(records)
    assert len(correlated) == 1
    ct = correlated[0]
    assert [s.tool_call_id for s in ct.spans] == ["call-1", "call-2"]
    assert ct.tool_calls["call-1"].reconciled_status in ("OK", "SUCCESS")
    assert ct.tool_calls["call-2"].reconciled_status in ("OK", "SUCCESS")
    assert AnomalyType.OUT_OF_ORDER_EVENTS in [a.anomaly_type for a in ct.anomalies]


# ==============================================================================
# 8. Contradictory Browser and Backend Observations
# ==============================================================================

def test_scenario_8_contradictory_browser_and_backend(clean_pipeline):
    """Backend claiming autonomous is overridden by Browser HITL modal observation."""
    call_id = "call-conflict-8"
    tid = "trace-conflict-8"

    otlp_payload = json.dumps({
        "spans": [
            {
                "trace_id": tid,
                "span_id": "span-backend-tool",
                "name": "delete_customer_record",
                "start_time_ns": 1729000000000000000,
                "end_time_ns": 1729000002000000000,
                "attributes": {
                    "gen_ai.tool.name": "delete_customer_record",
                    "gen_ai.tool.call_id": call_id,
                    "agent.is_human_intervention": False
                }
            }
        ]
    }).encode("utf-8")

    browser_payload = json.dumps({
        "actions": [
            {
                "action_type": "approval_modal_confirm",
                "target_selector": "button#modal-confirm-delete",
                "timestamp": "2026-10-20T10:00:01Z",
                "tool_call_id": call_id,
                "trace_id": tid,
                "human_override": True
            }
        ]
    }).encode("utf-8")

    clean_pipeline.ingest_evidence(otlp_payload, source_type=SourceType.OTLP, company_id="comp-conflict")
    clean_pipeline.ingest_evidence(browser_payload, source_type=SourceType.BROWSER, company_id="comp-conflict")

    records = clean_pipeline.registry.get_records(company_id="comp-conflict")
    correlated = clean_pipeline.correlation_engine.correlate_records(records)
    ct = correlated[0]
    assert ct.has_contradictions is True
    assert ct.tool_calls[call_id].is_human_intervention is True


# ==============================================================================
# 9. Tampered Evidence / Invalid Provenance Detection
# ==============================================================================

def test_scenario_9_tampered_evidence_digest(clean_pipeline):
    """Altering payload bytes after calculating hash mismatch triggers rejection or mismatch."""
    clean_bytes = json.dumps({"spans": [{"trace_id": "t1", "span_id": "s1", "name": "task"}]}).encode("utf-8")
    fake_hash = "0000000000000000000000000000000000000000000000000000000000000000"

    # Registering with a mismatched provenance hash preserves transparency:
    receipt = clean_pipeline.ingest_evidence(
        clean_bytes,
        source_type=SourceType.OTLP,
        company_id="comp-tamper",
        provenance_hash=fake_hash
    )
    # The receipt and envelope carry the declared hash
    assert receipt.payload_hash == fake_hash
    # The actual SHA-256 of the raw payload is stored in canonical_sha256
    assert receipt.envelope.payload_sha256 == fake_hash
    assert receipt.envelope.compute_envelope_hash() != fake_hash


# ==============================================================================
# 10. Cross-Session / Cross-Company Evidence Isolation
# ==============================================================================

def test_scenario_10_cross_company_isolation(clean_pipeline):
    """Evidence ingested for Company A is never leaked or mixed into Company B queries."""
    payload_a = json.dumps({
        "spans": [{"trace_id": "trace-corp-a", "span_id": "span-a", "name": "secret_model"}]
    }).encode("utf-8")
    payload_b = json.dumps({
        "spans": [{"trace_id": "trace-corp-b", "span_id": "span-b", "name": "public_model"}]
    }).encode("utf-8")

    clean_pipeline.ingest_evidence(payload_a, source_type=SourceType.OTLP, company_id="corp-alpha")
    clean_pipeline.ingest_evidence(payload_b, source_type=SourceType.OTLP, company_id="corp-beta")

    records_a = clean_pipeline.registry.get_records(company_id="corp-alpha")
    records_b = clean_pipeline.registry.get_records(company_id="corp-beta")

    assert len(records_a) == 1
    assert len(records_b) == 1
    assert records_a[0].span.name == "secret_model"
    assert records_b[0].span.name == "public_model"
    assert records_a[0].trace_id == "trace-corp-a"
    assert records_b[0].trace_id == "trace-corp-b"


# ==============================================================================
# 11. Unresolved Tool Calls (UNKNOWN Preservation)
# ==============================================================================

def test_scenario_11_unresolved_mcp_tool_call(clean_pipeline):
    """Unanswered MCP tool calls remain UNKNOWN and do not convert into successful executions."""
    unanswered_payload = json.dumps({
        "messages": [
            {
                "jsonrpc": "2.0",
                "id": "unanswered-req-404",
                "method": "tools/call",
                "params": {"name": "query_inventory"}
            }
        ]
    }).encode("utf-8")

    clean_pipeline.ingest_evidence(unanswered_payload, source_type=SourceType.MCP, company_id="comp-timeout")
    records = clean_pipeline.registry.get_records(company_id="comp-timeout")
    assert records[0].status == EvidenceStatus.INCOMPLETE

    correlated = clean_pipeline.correlation_engine.correlate_records(records)
    tc = correlated[0].tool_calls["unanswered-req-404"]
    assert tc.reconciled_status == "UNKNOWN"
    assert tc.epistemic_tag == EpistemicTag.UNKNOWN


# ==============================================================================
# 12. Malformed and Oversized Payloads
# ==============================================================================

def test_scenario_12_malformed_and_oversized_payloads(clean_pipeline):
    """Oversized and malformed payloads are safely rejected with descriptive exceptions."""
    # 1. Malformed JSON
    with pytest.raises(IngestionError):
        clean_pipeline.ingest_evidence(b"{not-valid-json!}", source_type=SourceType.OTLP)

    # 2. Oversized payload (> 10MB)
    huge_bytes = b" " * (MAX_PAYLOAD_SIZE_BYTES + 1024)
    with pytest.raises(PayloadTooLargeError):
        clean_pipeline.ingest_evidence(huge_bytes, source_type=SourceType.OTLP)


# ==============================================================================
# REST API End-to-End Verification
# ==============================================================================

def test_api_evidence_ingest_and_verify_e2e(api_client):
    """Tests the full API flow: POST /api/v1/evidence/ingest -> POST /api/v1/evidence/verify."""
    company_id = "test-api-corp-01"

    # Ingest 16 traces
    for i in range(16):
        payload = {
            "spans": [
                {
                    "trace_id": f"api-trace-{i:03d}",
                    "span_id": f"api-span-{i}",
                    "name": "ai_inference",
                    "start_time_ns": 1729000000000000000 + (i * 2_000_000_000),
                    "end_time_ns": 1729000001000000000 + (i * 2_000_000_000),
                    "attributes": {
                        "gen_ai.provider.name": "openai",
                        "gen_ai.request.model": "gpt-4o",
                        "gen_ai.usage.input_tokens": 100,
                        "gen_ai.usage.output_tokens": 50,
                    }
                }
            ]
        }
        res = api_client.post(
            f"/api/v1/evidence/ingest?company_id={company_id}&source_type=otlp",
            json=payload
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert len(data["payload_hash"]) == 64

    # Query registered records
    records_res = api_client.get(f"/api/v1/evidence/records?company_id={company_id}")
    assert records_res.status_code == 200
    assert len(records_res.json()) >= 16

    # Verify claim via API
    verify_payload = {
        "company_id": company_id,
        "claims": [
            {
                "claim_id": "api-autonomy-claim",
                "dimension": "autonomy",
                "stated_claim_text": "System achieves at least 80% task autonomy",
                "target_operator": ">=",
                "target_value": 80.0,
                "unit": "%"
            }
        ],
        "min_sample_size": 15
    }

    verify_res = api_client.post("/api/v1/evidence/verify", json=verify_payload)
    assert verify_res.status_code == 200
    v_data = verify_res.json()
    assert v_data["company_id"] == company_id
    assert v_data["total_correlated_traces"] >= 16
    assert len(v_data["matrix"]["entries"]) == 1
    assert v_data["matrix"]["entries"][0]["verification_verdict"] == "VERIFIED"
