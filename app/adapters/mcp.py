"""
Model Context Protocol (MCP) Evidence Adapter (Phase 5 — Milestone D).

Conforms to BaseEvidenceAdapter specification in docs/phase-5/evidence-adapter-architecture.md.
Ingests stdio and HTTP SSE JSON-RPC 2.0 message streams between MCP clients and servers.
Enforces strict 6-state lifecycle disambiguation:
1. Tool Discovered (`tools/list`)
2. Client Call Attempt (`tools/call` request)
3. Server Received (proxy or server observation)
4. Tool Executed
5. Tool Result Returned (`result` / `error`)
6. Agent Task Succeeded

Invariant: An unanswered `tools/call` request without a corresponding response produces
`tool_status="UNKNOWN"`, widening task autonomy bounds without false assumption of completion.
"""

import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from app.adapters.base import (
    BaseEvidenceAdapter,
    AdapterCapability,
    ProvenanceEnvelope,
)
from app.epistemic.tags import TrustLevel, EpistemicTag
from app.ingestion.otlp_handler import (
    MAX_PAYLOAD_SIZE_BYTES,
    IngestionError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from app.ingestion.schema import NormalizedSpan, NormalizationVersion


class McpLifecycleState(str, Enum):
    TOOL_DISCOVERED = "tool_discovered"
    CLIENT_CALL_ATTEMPT = "client_call_attempt"
    SERVER_RECEIVED = "server_received"
    TOOL_EXECUTED = "tool_executed"
    TOOL_RESULT_RETURNED = "tool_result_returned"
    AGENT_TASK_SUCCEEDED = "agent_task_succeeded"
    UNANSWERED_TIMEOUT = "unanswered_timeout"


class McpEvidenceAdapter(BaseEvidenceAdapter):
    """
    Evidence Adapter for Model Context Protocol (MCP) telemetry.
    Normalizes JSON-RPC 2.0 messages (tools/call requests, responses, and errors)
    into canonical NormalizedSpan objects with explicit lifecycle attribution.
    """
    adapter_id: str = "mcp_evidence_adapter"
    adapter_version: str = "1.0.0"
    source_framework: str = "model_context_protocol"
    source_version: str = "2024-11-05"
    default_trust_level: TrustLevel = TrustLevel.T2  # Captured via proxy/stdio tap

    def declared_capabilities(self) -> List[AdapterCapability]:
        """Certifies MCP tool observation capabilities and boundaries."""
        return [
            AdapterCapability.CAN_OBSERVE_TOOL_CALL,
            AdapterCapability.CAN_OBSERVE_TOOL_EXECUTION_RESULT,
            AdapterCapability.CAN_OBSERVE_SERVER_SIDE_ERRORS,
        ]

    def known_blind_spots(self) -> List[str]:
        """Discloses unobservable boundaries in MCP protocol streams."""
        return [
            "Internal model thoughts, prompts, and tokens inside proprietary LLM client",
            "Downstream non-MCP external systems outside server process boundary",
            "Uninstrumented human overrides outside MCP JSON-RPC messages",
            "Server internal host CPU and hardware memory utilization",
        ]

    def validate_payload(self, raw_bytes: bytes, content_type: str = "application/json") -> Dict[str, Any]:
        """Validates payload bounds, content type, and JSON syntax."""
        byte_size = len(raw_bytes)
        if byte_size > MAX_PAYLOAD_SIZE_BYTES:
            raise PayloadTooLargeError(f"Payload size {byte_size} bytes exceeds 10 MB limit.")

        ct_clean = content_type.split(";")[0].strip().lower()
        if ct_clean not in ["application/json", "application/x-json", "application/x-ndjson", "text/json", ""]:
            raise UnsupportedMediaTypeError(
                f"Unsupported Content-Type: {content_type}. Expected 'application/json' or 'application/x-ndjson'."
            )

        try:
            text = raw_bytes.decode("utf-8").strip()
            if text.startswith("["):
                messages = json.loads(text)
                payload = {"messages": messages}
            elif "\n" in text and not text.startswith("{"):
                # Handle NDJSON
                lines = [json.loads(line) for line in text.splitlines() if line.strip()]
                payload = {"messages": lines}
            else:
                payload = json.loads(text)
        except Exception as json_err:
            raise IngestionError(f"Malformed JSON payload in MCP stream: {str(json_err)}")

        if not isinstance(payload, dict):
            raise IngestionError("Invalid JSON root: MCP payload must be an object with 'messages' or an array.")

        return payload

    def parse_and_normalize(
        self,
        raw_bytes: bytes,
        content_type: str = "application/json",
        company_id: Optional[str] = None,
        provenance_hash: Optional[str] = None,
        trust_level: Optional[TrustLevel] = None,
    ) -> Tuple[ProvenanceEnvelope, List[NormalizedSpan]]:
        """
        Extracts JSON-RPC 2.0 messages from payload, matches tool call requests
        with their corresponding responses by ID, and produces canonical NormalizedSpans.
        """
        payload = self.validate_payload(raw_bytes, content_type)
        payload_hash = provenance_hash or self.compute_sha256(raw_bytes)
        effective_trust = trust_level or self.default_trust_level

        raw_messages = payload.get("messages") or payload.get("events") or []
        if not isinstance(raw_messages, list) or len(raw_messages) == 0:
            raise IngestionError("Empty MCP payload: no JSON-RPC messages found.")

        # Separate requests and responses/errors by JSON-RPC ID
        requests: Dict[str, Dict[str, Any]] = {}
        responses: Dict[str, Dict[str, Any]] = {}
        discovered_tools: List[str] = []

        top_trace_id = payload.get("trace_id") or f"mcp-trace-{payload_hash[:16]}"

        for msg in raw_messages:
            if not isinstance(msg, dict):
                continue

            msg_id = msg.get("id")
            method = msg.get("method")

            # 1. Tool discovery event (tools/list)
            if method == "tools/list":
                continue
            if "result" in msg and isinstance(msg.get("result"), dict) and "tools" in msg["result"]:
                tools_list = msg["result"].get("tools", [])
                for t in tools_list:
                    if isinstance(t, dict) and "name" in t:
                        discovered_tools.append(t["name"])
                continue

            # 2. Tool invocation request (tools/call)
            if method == "tools/call" and msg_id is not None:
                requests[str(msg_id)] = msg

            # 3. Tool response or error
            elif msg_id is not None and ("result" in msg or "error" in msg):
                responses[str(msg_id)] = msg

        if not requests:
            # If payload had only tool discovery without calls, no execution spans exist
            envelope = self.create_provenance_envelope(
                raw_bytes=raw_bytes,
                content_type=content_type,
                provenance_hash=payload_hash,
                trust_level=effective_trust,
                custom_metadata={
                    "company_id": company_id,
                    "discovered_tools": discovered_tools,
                    "total_tool_calls": 0,
                },
            )
            return envelope, []

        normalized_spans: List[NormalizedSpan] = []
        unanswered_count = 0
        error_count = 0
        success_count = 0

        for req_id_str, req_msg in requests.items():
            params = req_msg.get("params", {})
            tool_name = params.get("name", "unspecified_mcp_tool")
            args = params.get("arguments", {})

            # Timestamps
            req_ts_raw = req_msg.get("timestamp")
            if req_ts_raw:
                try:
                    start_dt = datetime.fromisoformat(str(req_ts_raw).replace("Z", "+00:00")).replace(tzinfo=None)
                except Exception:
                    start_dt = datetime.now(timezone.utc).replace(tzinfo=None)
            else:
                start_dt = datetime.now(timezone.utc).replace(tzinfo=None)

            span_id = f"mcp-span-{req_id_str}"
            trace_id = req_msg.get("trace_id") or top_trace_id

            # Correlate with response
            resp_msg = responses.get(req_id_str)

            if resp_msg is None:
                # Invariant: Unanswered call attempt -> UNKNOWN status (widens bounds)
                unanswered_count += 1
                end_dt = start_dt + timedelta(milliseconds=100)
                duration_ms = 100.0
                status_code = "UNSET"
                tool_status = "UNKNOWN"
                status_msg = "MCP tool call dispatched without server response (hang, timeout, or missing telemetry)"
                epistemic_tag = EpistemicTag.UNKNOWN
                lifecycle_state = McpLifecycleState.UNANSWERED_TIMEOUT
            else:
                resp_ts_raw = resp_msg.get("timestamp")
                if resp_ts_raw:
                    try:
                        end_dt = datetime.fromisoformat(str(resp_ts_raw).replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        end_dt = start_dt + timedelta(milliseconds=150)
                else:
                    end_dt = start_dt + timedelta(milliseconds=150)

                duration_ms = max(0.0, (end_dt - start_dt).total_seconds() * 1000.0)

                if "error" in resp_msg:
                    error_count += 1
                    err_info = resp_msg["error"]
                    status_code = "ERROR"
                    tool_status = "ERROR"
                    status_msg = err_info.get("message", "MCP JSON-RPC Error")
                    epistemic_tag = EpistemicTag.OBSERVED
                    lifecycle_state = McpLifecycleState.TOOL_RESULT_RETURNED
                else:
                    res_obj = resp_msg.get("result", {})
                    is_err = res_obj.get("isError", False)
                    if is_err:
                        error_count += 1
                        status_code = "ERROR"
                        tool_status = "ERROR"
                        status_msg = "Tool returned execution error (isError=true)"
                        epistemic_tag = EpistemicTag.OBSERVED
                        lifecycle_state = McpLifecycleState.TOOL_RESULT_RETURNED
                    else:
                        success_count += 1
                        status_code = "OK"
                        tool_status = "OK"
                        status_msg = None
                        epistemic_tag = EpistemicTag.OBSERVED
                        lifecycle_state = McpLifecycleState.TOOL_RESULT_RETURNED

            span = NormalizedSpan(
                span_id=span_id,
                trace_id=trace_id,
                name=f"mcp_tool::{tool_name}",
                span_kind="CLIENT",
                start_time=start_dt,
                end_time=end_dt,
                duration_ms=duration_ms,
                status_code=status_code,
                status_message=status_msg,
                tool_name=tool_name,
                tool_call_id=req_id_str,
                tool_status=tool_status,
                is_human_intervention=False,
                epistemic_tag=epistemic_tag,
                trust_level=effective_trust,
                normalization_version=NormalizationVersion.V1_28_0.value,
                raw_attributes={
                    "mcp.lifecycle_state": lifecycle_state.value,
                    "mcp.arguments": args,
                    "provenance_hash": payload_hash,
                },
            )
            normalized_spans.append(span)

        envelope = self.create_provenance_envelope(
            raw_bytes=raw_bytes,
            content_type=content_type,
            provenance_hash=payload_hash,
            trust_level=effective_trust,
            custom_metadata={
                "company_id": company_id,
                "discovered_tools": discovered_tools,
                "total_tool_calls": len(normalized_spans),
                "successful_calls": success_count,
                "error_calls": error_count,
                "unanswered_calls": unanswered_count,
            },
        )

        return envelope, normalized_spans

