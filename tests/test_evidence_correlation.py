"""
Unit Tests for Evidence Correlation Engine (Phase 6 — Milestone B).

Validates:
- Cross-adapter correlation by trace_id, span_id, session_id, tool_call_id
- Causal ordering of out-of-order events
- Missing parent span quarantine (no relationship fabrication)
- Clock skew detection
- Incomplete tool call status preservation (epistemic UNKNOWN)
- Multi-tier observer contradiction reconciliation (T2 MCP over T1 OTLP; Browser HITL signals)
- Uninstrumented dark zone detection
"""

import json
from datetime import datetime, timezone, timedelta
import pytest

from app.adapters.registry import (
    UnifiedEvidenceRegistry,
    SourceType,
    EvidenceStatus,
    compute_deterministic_evidence_id,
)
from app.adapters.correlation import (
    EvidenceCorrelationEngine,
    AnomalyType,
    CorrelatedTrace,
)
from app.epistemic.tags import EpistemicTag, TrustLevel


@pytest.fixture
def engine():
    return EvidenceCorrelationEngine(gap_threshold_ms=30000.0)


@pytest.fixture
def registry():
    reg = UnifiedEvidenceRegistry()
    reg.clear()
    return reg


def test_correlate_causal_sorting_out_of_order(engine, registry):
    """Spans arriving reversed are causally ordered by start time, and anomaly is logged."""
    t0 = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=2)
    t2 = t0 + timedelta(seconds=5)

    # Intentionally out-of-order: span 2, span 1, span 0
    payload = json.dumps({
        "spans": [
            {
                "trace_id": "trace-order-01",
                "span_id": "span-3",
                "name": "step_3",
                "start_time_ns": int(t2.timestamp() * 1e9),
                "end_time_ns": int((t2 + timedelta(seconds=1)).timestamp() * 1e9),
                "attributes": {}
            },
            {
                "trace_id": "trace-order-01",
                "span_id": "span-2",
                "name": "step_2",
                "start_time_ns": int(t1.timestamp() * 1e9),
                "end_time_ns": int((t1 + timedelta(seconds=1)).timestamp() * 1e9),
                "attributes": {}
            },
            {
                "trace_id": "trace-order-01",
                "span_id": "span-1",
                "name": "step_1",
                "start_time_ns": int(t0.timestamp() * 1e9),
                "end_time_ns": int((t0 + timedelta(seconds=1)).timestamp() * 1e9),
                "attributes": {}
            }
        ]
    }).encode("utf-8")

    receipt = registry.register_payload(payload, source_type=SourceType.OTLP)
    records = registry.get_records(trace_id="trace-order-01")

    correlated = engine.correlate_records(records)
    assert len(correlated) == 1
    ct = correlated[0]

    # Spans must be ordered: span-1, span-2, span-3
    assert [s.span_id for s in ct.spans] == ["span-1", "span-2", "span-3"]
    anom_types = [a.anomaly_type for a in ct.anomalies]
    assert AnomalyType.OUT_OF_ORDER_EVENTS in anom_types


def test_missing_parent_span_not_fabricated(engine, registry):
    """Child span referencing non-existent parent logs MISSING_PARENT_SPAN and is preserved as root."""
    payload = json.dumps({
        "spans": [
            {
                "trace_id": "trace-orphan-01",
                "span_id": "span-orphan-child",
                "parent_span_id": "non-existent-parent-span",
                "name": "child_task",
                "start_time_ns": 1729000000000000000,
                "end_time_ns": 1729000001000000000,
                "attributes": {}
            }
        ]
    }).encode("utf-8")

    registry.register_payload(payload, source_type=SourceType.OTLP)
    records = registry.get_records(trace_id="trace-orphan-01")

    correlated = engine.correlate_records(records)
    assert len(correlated) == 1
    ct = correlated[0]

    assert len(ct.spans) == 1
    assert ct.spans[0].span_id == "span-orphan-child"
    anom_types = [a.anomaly_type for a in ct.anomalies]
    assert AnomalyType.MISSING_PARENT_SPAN in anom_types


def test_clock_skew_detection(engine, registry):
    """Span with negative duration triggers CLOCK_SKEW anomaly."""
    t0 = datetime(2026, 10, 20, 10, 0, 5, tzinfo=timezone.utc)
    t_earlier = datetime(2026, 10, 20, 10, 0, 1, tzinfo=timezone.utc)

    payload = json.dumps({
        "spans": [
            {
                "trace_id": "trace-skew-01",
                "span_id": "span-skew",
                "name": "skewed_task",
                "start_time_ns": int(t0.timestamp() * 1e9),
                "end_time_ns": int(t_earlier.timestamp() * 1e9),  # end < start!
                "attributes": {}
            }
        ]
    }).encode("utf-8")

    registry.register_payload(payload, source_type=SourceType.OTLP)
    records = registry.get_records(trace_id="trace-skew-01")

    correlated = engine.correlate_records(records)
    ct = correlated[0]
    anom_types = [a.anomaly_type for a in ct.anomalies]
    assert AnomalyType.CLOCK_SKEW in anom_types


def test_incomplete_tool_execution_reconciled_as_unknown(engine, registry):
    """Unanswered MCP tool request remains UNKNOWN and does not become success."""
    payload = json.dumps({
        "messages": [
            {
                "jsonrpc": "2.0",
                "id": "tool-call-unresolved-123",
                "method": "tools/call",
                "params": {"name": "execute_query", "arguments": {"q": "SELECT 1;"}}
            }
        ]
    }).encode("utf-8")

    registry.register_payload(payload, source_type=SourceType.MCP)
    records = registry.get_records()

    correlated = engine.correlate_records(records)
    assert len(correlated) == 1
    ct = correlated[0]

    assert ct.has_incomplete_tools is True
    tc = list(ct.tool_calls.values())[0]
    assert tc.reconciled_status == "UNKNOWN"
    assert tc.epistemic_tag == EpistemicTag.UNKNOWN


def test_contradiction_t2_mcp_downgrades_t1_otlp(engine, registry):
    """
    When T1 OTLP claims tool execution was OK, but T2 MCP proxy observed an ERROR:
    T2 takes precedence, reconciled status is ERROR, and CONTRADICTORY_OBSERVATION anomaly is logged.
    """
    call_id = "shared-call-conflict-999"
    tid = "trace-conflict-01"

    otlp_payload = json.dumps({
        "spans": [
            {
                "trace_id": tid,
                "span_id": "span-otlp-client",
                "name": "db_query",
                "start_time_ns": 1729000000000000000,
                "end_time_ns": 1729000001000000000,
                "status": {"code": 1},  # OK
                "attributes": {
                    "gen_ai.tool.name": "db_query",
                    "gen_ai.tool.call.id": call_id,
                    "gen_ai.tool.status": "SUCCESS"
                }
            }
        ]
    }).encode("utf-8")

    mcp_payload = json.dumps({
        "messages": [
            {
                "jsonrpc": "2.0",
                "id": call_id,
                "method": "tools/call",
                "params": {"name": "db_query", "arguments": {}}
            },
            {
                "jsonrpc": "2.0",
                "id": call_id,
                "error": {"code": -32000, "message": "Database query connection failure"}
            }
        ]
    }).encode("utf-8")

    registry.register_payload(otlp_payload, source_type=SourceType.OTLP)
    # Register MCP with same trace_id
    registry.register_payload(mcp_payload, source_type=SourceType.MCP)

    # In MCP adapter, spans get a trace_id; let's link or correlate by call_id
    records = registry.get_records()
    # Ensure MCP span has matching trace_id for correlation
    for r in records:
        if r.source_type == SourceType.MCP:
            r.trace_id = tid
            r.span.trace_id = tid

    correlated = engine.correlate_records(records)
    ct = [c for c in correlated if c.trace_id == tid][0]

    assert ct.has_contradictions is True
    tc = ct.tool_calls[call_id]
    assert tc.reconciled_status == "ERROR"
    assert tc.trust_level == TrustLevel.T2
    anom_types = [a.anomaly_type for a in ct.anomalies]
    assert AnomalyType.CONTRADICTORY_OBSERVATION in anom_types


def test_contradiction_browser_approval_modal_reconciles_human_intervention(engine, registry):
    """
    When OTLP claims autonomous execution, but Browser adapter observes an approval modal click:
    Reconciled state is marked is_human_intervention = True, and contradiction is flagged.
    """
    tid = "trace-human-override-01"
    call_id = "deploy-call-42"

    otlp_payload = json.dumps({
        "spans": [
            {
                "trace_id": tid,
                "span_id": "span-otlp-deploy",
                "name": "deploy_prod",
                "start_time_ns": 1729000000000000000,
                "end_time_ns": 1729000002000000000,
                "attributes": {
                    "gen_ai.tool.name": "deploy_prod",
                    "gen_ai.tool.call.id": call_id,
                    "agent.is_human_intervention": False
                }
            }
        ]
    }).encode("utf-8")

    browser_payload = json.dumps({
        "actions": [
            {
                "action_type": "click",
                "target_selector": "button#approve-deploy-modal",
                "timestamp_utc": "2026-10-20T10:00:01Z",
                "modal_text": "Confirm production deployment",
                "human_override": True,
                "tool_call_id": call_id,
                "trace_id": tid
            }
        ]
    }).encode("utf-8")

    registry.register_payload(otlp_payload, source_type=SourceType.OTLP)
    registry.register_payload(browser_payload, source_type=SourceType.BROWSER)

    records = registry.get_records(trace_id=tid)
    correlated = engine.correlate_records(records)
    ct = correlated[0]

    assert ct.has_contradictions is True
    tc = ct.tool_calls[call_id]
    assert tc.is_human_intervention is True
    assert any(s.is_human_intervention for s in ct.spans)


def test_uninstrumented_dark_zone_detected(engine, registry):
    """Gaps > 30s between consecutive spans generate DARK_ZONE_GAP anomalies."""
    t0 = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=10)
    t2 = t1 + timedelta(seconds=70)  # 70s gap > 30s threshold

    payload = json.dumps({
        "spans": [
            {
                "trace_id": "trace-dark-01",
                "span_id": "span-before-gap",
                "name": "task_1",
                "start_time_ns": int(t0.timestamp() * 1e9),
                "end_time_ns": int(t1.timestamp() * 1e9),
                "attributes": {}
            },
            {
                "trace_id": "trace-dark-01",
                "span_id": "span-after-gap",
                "name": "task_2",
                "start_time_ns": int(t2.timestamp() * 1e9),
                "end_time_ns": int((t2 + timedelta(seconds=5)).timestamp() * 1e9),
                "attributes": {}
            }
        ]
    }).encode("utf-8")

    registry.register_payload(payload, source_type=SourceType.OTLP)
    records = registry.get_records(trace_id="trace-dark-01")

    correlated = engine.correlate_records(records)
    ct = correlated[0]

    assert len(ct.dark_zones) == 1
    assert ct.dark_zones[0]["gap_duration_ms"] == 70000.0
    anom_types = [a.anomaly_type for a in ct.anomalies]
    assert AnomalyType.DARK_ZONE_GAP in anom_types


def test_unlinked_observation_quarantine(engine, registry):
    """Record without trace identifier is never arbitrarily linked to an existing trace."""
    registry.register_payload(
        json.dumps({
            "spans": [
                {
                    "trace_id": "temp-tid",
                    "span_id": "isolated-span-1",
                    "name": "isolated_task",
                    "start_time_ns": 1729000000000000000,
                    "end_time_ns": 1729000001000000000,
                    "attributes": {}
                }
            ]
        }).encode("utf-8"),
        source_type=SourceType.OTLP
    )
    records = registry.get_records()
    records[0].trace_id = ""
    records[0].span.trace_id = ""

    correlated = engine.correlate_records(records)

    unlinked_traces = [t for t in correlated if t.trace_id.startswith("unlinked-")]
    assert len(unlinked_traces) >= 1
    assert AnomalyType.UNLINKED_OBSERVATION in [a.anomaly_type for a in unlinked_traces[0].anomalies]
