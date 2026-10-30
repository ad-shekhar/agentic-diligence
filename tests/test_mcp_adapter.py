"""
Phase 5 Milestone D Tests: Model Context Protocol (MCP) Evidence Adapter.

Validates MCP JSON-RPC 2.0 message parsing, lifecycle disambiguation,
and epistemic unknown handling for unanswered tool requests.
"""

import hashlib
import json
import pytest
from datetime import datetime, timezone

from app.adapters.mcp import McpEvidenceAdapter, McpLifecycleState
from app.adapters.base import AdapterCapability
from app.epistemic.tags import TrustLevel, EpistemicTag
from app.analysis.task_segmentation import segment_trace, TaskOutcome
from app.ingestion.otlp_handler import (
    IngestionError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)


@pytest.fixture
def mcp_adapter():
    return McpEvidenceAdapter()


# ==============================================================================
# 1. Adapter Contract & Capability Tests
# ==============================================================================

def test_mcp_adapter_capabilities_and_metadata(mcp_adapter):
    """McpEvidenceAdapter declares expected T2 trust, MCP version, and observational capabilities."""
    assert mcp_adapter.adapter_id == "mcp_evidence_adapter"
    assert mcp_adapter.adapter_version == "1.0.0"
    assert mcp_adapter.source_framework == "model_context_protocol"
    assert mcp_adapter.source_version == "2024-11-05"
    assert mcp_adapter.default_trust_level == TrustLevel.T2

    caps = mcp_adapter.declared_capabilities()
    assert AdapterCapability.CAN_OBSERVE_TOOL_CALL in caps
    assert AdapterCapability.CAN_OBSERVE_TOOL_EXECUTION_RESULT in caps
    assert AdapterCapability.CAN_OBSERVE_SERVER_SIDE_ERRORS in caps

    blind_spots = mcp_adapter.known_blind_spots()
    assert len(blind_spots) >= 3
    assert any("model thoughts" in s.lower() for s in blind_spots)


def test_mcp_adapter_payload_validation(mcp_adapter):
    """Payload boundaries and media types are strictly enforced."""
    # Rejects > 10 MB
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    with pytest.raises(PayloadTooLargeError):
        mcp_adapter.validate_payload(oversized)

    # Rejects unsupported format
    with pytest.raises(UnsupportedMediaTypeError):
        mcp_adapter.validate_payload(b"{}", "application/xml")

    # Rejects malformed JSON
    with pytest.raises(IngestionError):
        mcp_adapter.validate_payload(b"{bad-json")

    # Rejects empty payload
    with pytest.raises(IngestionError):
        mcp_adapter.parse_and_normalize(b"[]")


# ==============================================================================
# 2. Tool Discovery & Lifecycle Disambiguation
# ==============================================================================

def test_mcp_adapter_tools_list_discovery_only(mcp_adapter):
    """Discovery messages (tools/list) disclose advertised tools without producing execution spans."""
    payload = {
        "messages": [
            {
                "jsonrpc": "2.0",
                "id": "init-1",
                "method": "tools/list",
                "params": {}
            },
            {
                "jsonrpc": "2.0",
                "id": "init-1",
                "result": {
                    "tools": [
                        {"name": "calculate_tax", "description": "Computes state tax"},
                        {"name": "query_database", "description": "Executes read query"}
                    ]
                }
            }
        ]
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    envelope, spans = mcp_adapter.parse_and_normalize(raw_bytes)

    # Invariant: Discovery alone does NOT generate execution spans
    assert len(spans) == 0
    assert "calculate_tax" in envelope.custom_metadata["discovered_tools"]
    assert "query_database" in envelope.custom_metadata["discovered_tools"]
    assert envelope.custom_metadata["total_tool_calls"] == 0


def test_mcp_adapter_successful_tool_call(mcp_adapter):
    """Successful tool execution maps to status_code=OK and tool_status=OK."""
    payload = {
        "trace_id": "mcp-trace-tax-001",
        "messages": [
            {
                "jsonrpc": "2.0",
                "id": "call-101",
                "method": "tools/call",
                "timestamp": "2026-10-23T10:00:00Z",
                "params": {
                    "name": "calculate_tax",
                    "arguments": {"amount": 250.0, "state": "NY"}
                }
            },
            {
                "jsonrpc": "2.0",
                "id": "call-101",
                "timestamp": "2026-10-23T10:00:00.085Z",
                "result": {
                    "content": [{"type": "text", "text": "{\"tax\": 22.18}"}],
                    "isError": False
                }
            }
        ]
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    envelope, spans = mcp_adapter.parse_and_normalize(raw_bytes)

    assert len(spans) == 1
    span = spans[0]
    assert span.tool_name == "calculate_tax"
    assert span.tool_call_id == "call-101"
    assert span.tool_status == "OK"
    assert span.status_code == "OK"
    assert span.duration_ms == pytest.approx(85.0, abs=1.0)
    assert span.epistemic_tag == EpistemicTag.OBSERVED
    assert span.trust_level == TrustLevel.T2
    assert span.raw_attributes["mcp.lifecycle_state"] == McpLifecycleState.TOOL_RESULT_RETURNED.value
    assert envelope.custom_metadata["successful_calls"] == 1


def test_mcp_adapter_tool_execution_error_is_error(mcp_adapter):
    """Tool returning result with isError=true is attributed as ERROR."""
    payload = {
        "messages": [
            {
                "jsonrpc": "2.0",
                "id": "call-err-01",
                "method": "tools/call",
                "timestamp": "2026-10-23T10:00:00Z",
                "params": {
                    "name": "query_database",
                    "arguments": {"sql": "SELECT * FROM users"}
                }
            },
            {
                "jsonrpc": "2.0",
                "id": "call-err-01",
                "timestamp": "2026-10-23T10:00:00.120Z",
                "result": {
                    "content": [{"type": "text", "text": "Permission denied for table users"}],
                    "isError": True
                }
            }
        ]
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    envelope, spans = mcp_adapter.parse_and_normalize(raw_bytes)

    assert len(spans) == 1
    span = spans[0]
    assert span.tool_name == "query_database"
    assert span.tool_status == "ERROR"
    assert span.status_code == "ERROR"
    assert "isError=true" in span.status_message
    assert envelope.custom_metadata["error_calls"] == 1


def test_mcp_adapter_jsonrpc_protocol_error(mcp_adapter):
    """Server-side JSON-RPC protocol error is attributed with error message."""
    payload = {
        "messages": [
            {
                "jsonrpc": "2.0",
                "id": "call-proto-err",
                "method": "tools/call",
                "timestamp": "2026-10-23T10:00:00Z",
                "params": {
                    "name": "calculate_tax",
                    "arguments": {"amount": -10}
                }
            },
            {
                "jsonrpc": "2.0",
                "id": "call-proto-err",
                "timestamp": "2026-10-23T10:00:00.040Z",
                "error": {
                    "code": -32602,
                    "message": "Invalid params: amount must be positive"
                }
            }
        ]
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    envelope, spans = mcp_adapter.parse_and_normalize(raw_bytes)

    assert len(spans) == 1
    span = spans[0]
    assert span.tool_status == "ERROR"
    assert span.status_code == "ERROR"
    assert "Invalid params" in span.status_message


def test_mcp_adapter_unanswered_call_attempt_invariant(mcp_adapter):
    """
    Critical Invariant: An unanswered tool call attempt produces tool_status='UNKNOWN'.
    It must NEVER be recorded as completed or failed without proof.
    """
    payload = {
        "messages": [
            {
                "jsonrpc": "2.0",
                "id": "call-timeout-099",
                "method": "tools/call",
                "timestamp": "2026-10-23T10:00:00Z",
                "params": {
                    "name": "calculate_tax",
                    "arguments": {"amount": 500}
                }
            }
            # Note: No response message in stream (simulating network drop, hang, or process crash)
        ]
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    envelope, spans = mcp_adapter.parse_and_normalize(raw_bytes)

    assert len(spans) == 1
    span = spans[0]
    assert span.tool_status == "UNKNOWN"
    assert span.status_code == "UNSET"
    assert span.epistemic_tag == EpistemicTag.UNKNOWN
    assert span.raw_attributes["mcp.lifecycle_state"] == McpLifecycleState.UNANSWERED_TIMEOUT.value
    assert envelope.custom_metadata["unanswered_calls"] == 1


# ==============================================================================
# 3. Task Segmentation Integration
# ==============================================================================

def test_mcp_spans_task_segmentation_integration(mcp_adapter):
    """MCP normalized spans feed seamlessly into existing segment_trace engine."""
    payload = {
        "trace_id": "trace-mcp-e2e-001",
        "messages": [
            {
                "jsonrpc": "2.0",
                "id": "e2e-1",
                "method": "tools/call",
                "timestamp": "2026-10-23T10:00:00Z",
                "params": {"name": "query_database", "arguments": {}}
            },
            {
                "jsonrpc": "2.0",
                "id": "e2e-1",
                "timestamp": "2026-10-23T10:00:00.100Z",
                "result": {"content": [{"type": "text", "text": "rows: 10"}], "isError": False}
            }
        ]
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    _, spans = mcp_adapter.parse_and_normalize(raw_bytes)

    # Segment the trace
    seg = segment_trace(spans, trace_id="trace-mcp-e2e-001")
    assert seg.total_tasks == 1
    task = seg.tasks[0]
    assert task.name == "mcp_tool::query_database"
    assert task.outcome == TaskOutcome.AUTONOMOUS
    assert seg.autonomy.bounds.point_estimate == 100.0

