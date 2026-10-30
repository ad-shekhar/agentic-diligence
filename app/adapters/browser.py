"""
Browser Action Evidence Adapter (Phase 5 — Milestone E Specification Prototype).

Conforms to BaseEvidenceAdapter specification in docs/phase-5/evidence-adapter-architecture.md.
Ingests user-authorized browser action telemetry envelopes emitted by web extension clients.
Enforces strict client-side data privacy boundaries:
1. Strips all full DOM trees and raw HTML dumps.
2. Scrubbing of credit card numbers, passwords, API keys, and cookie headers.
3. Maps human confirmation/rejection modals directly to explicit human intervention signals.
"""

import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Set

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


class BrowserActionType(str, Enum):
    CLICK = "click"
    NAVIGATION = "navigation"
    INPUT_TEXT = "input_text"
    APPROVAL_MODAL_CONFIRM = "approval_modal_confirm"
    APPROVAL_MODAL_REJECT = "approval_modal_reject"
    PAGE_LOAD = "page_load"
    TOOL_TRIGGER = "tool_trigger"


# Privacy Redaction Regexes
_CREDIT_CARD_REGEX = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
_AUTH_HEADER_REGEX = re.compile(r"(?i)(bearer\s+[a-zA-Z0-9_\-\.]{16,}|password|secret|token)")
_API_KEY_REGEX = re.compile(r"(?i)(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{30,})")


class BrowserEvidenceAdapter(BaseEvidenceAdapter):
    """
    Evidence Adapter for WebExtension / Browser Telemetry.
    Normalizes DOM actions, user approval modals, and page transitions
    while enforcing strict privacy boundaries.
    """
    adapter_id: str = "browser_action_adapter"
    adapter_version: str = "1.0.0"
    source_framework: str = "web_extension"
    source_version: str = "1.0.0"
    default_trust_level: TrustLevel = TrustLevel.T1

    def declared_capabilities(self) -> List[AdapterCapability]:
        """Certifies browser observation capabilities."""
        return [
            AdapterCapability.CAN_OBSERVE_HUMAN_INTERVENTION,
            AdapterCapability.CAN_OBSERVE_TOOL_CALL,
            AdapterCapability.CAN_OBSERVE_TOOL_EXECUTION_RESULT,
        ]

    def known_blind_spots(self) -> List[str]:
        """Formal disclosure of browser extension unobservable regions."""
        return [
            "Server-side LLM prompts, reasoning tokens, and API credentials",
            "Background worker processes outside the instrumented browser tab",
            "Uninstrumented private tabs, cross-origin iframes, and local password fields",
            "Network transport hops between extension and remote agent server",
        ]

    def validate_payload(self, raw_bytes: bytes, content_type: str = "application/json") -> Dict[str, Any]:
        """Validates payload bounds, content type, and JSON syntax."""
        byte_size = len(raw_bytes)
        if byte_size > MAX_PAYLOAD_SIZE_BYTES:
            raise PayloadTooLargeError(f"Payload size {byte_size} bytes exceeds 10 MB limit.")

        ct_clean = content_type.split(";")[0].strip().lower()
        if ct_clean not in ["application/json", "application/x-json", "text/json", ""]:
            raise UnsupportedMediaTypeError(
                f"Unsupported Content-Type: {content_type}. Expected 'application/json'."
            )

        try:
            payload = json.loads(raw_bytes.decode("utf-8"))
        except Exception as json_err:
            raise IngestionError(f"Malformed JSON payload in browser action stream: {str(json_err)}")

        if not isinstance(payload, dict):
            raise IngestionError("Invalid JSON root: Browser action payload must be a JSON object.")

        return payload

    def _redact_event(self, event: Dict[str, Any], redacted_list: List[str]) -> Dict[str, Any]:
        """Enforces privacy constraints by scrubbing sensitive data from event dictionary."""
        sanitized = dict(event)

        # 1. Eliminate full DOM trees or raw outerHTML
        for forbidden in ["dom_tree", "raw_html", "outer_html", "full_page_html"]:
            if forbidden in sanitized:
                del sanitized[forbidden]
                redacted_list.append(forbidden)

        # 2. Scrub sensitive input values
        if "input_value" in sanitized:
            val_str = str(sanitized["input_value"])
            if _CREDIT_CARD_REGEX.search(val_str) or _AUTH_HEADER_REGEX.search(val_str) or _API_KEY_REGEX.search(val_str):
                sanitized["input_value"] = "[REDACTED_SENSITIVE_CONTENT]"
                redacted_list.append("input_value")
            elif sanitized.get("is_password_field", False):
                sanitized["input_value"] = "[REDACTED_PASSWORD]"
                redacted_list.append("input_value")

        return sanitized

    def parse_and_normalize(
        self,
        raw_bytes: bytes,
        content_type: str = "application/json",
        company_id: Optional[str] = None,
        provenance_hash: Optional[str] = None,
        trust_level: Optional[TrustLevel] = None,
    ) -> Tuple[ProvenanceEnvelope, List[NormalizedSpan]]:
        """
        Parses browser action envelope, scrubs credentials and DOM trees,
        and converts action items into canonical NormalizedSpan objects.
        """
        payload = self.validate_payload(raw_bytes, content_type)
        payload_hash = provenance_hash or self.compute_sha256(raw_bytes)
        effective_trust = trust_level or self.default_trust_level

        raw_events = payload.get("actions") or payload.get("events") or []
        if not isinstance(raw_events, list) or len(raw_events) == 0:
            raise IngestionError("Empty browser action payload: no actions recorded.")

        top_trace_id = payload.get("trace_id") or f"browser-trace-{payload_hash[:16]}"
        redacted_fields: List[str] = []
        normalized_spans: List[NormalizedSpan] = []

        human_modals_observed = 0

        for idx, event in enumerate(raw_events):
            if not isinstance(event, dict):
                continue

            cleaned_event = self._redact_event(event, redacted_fields)

            action_type = cleaned_event.get("action_type", BrowserActionType.CLICK.value)
            action_id = cleaned_event.get("action_id", f"act-{idx:03d}")
            selector = cleaned_event.get("target_selector", "unknown_element")

            # Timestamps
            ts_raw = cleaned_event.get("timestamp") or cleaned_event.get("timestamp_utc")
            if ts_raw:
                try:
                    start_dt = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")).replace(tzinfo=None)
                except Exception:
                    start_dt = datetime.now(timezone.utc).replace(tzinfo=None)
            else:
                start_dt = datetime.now(timezone.utc).replace(tzinfo=None)

            duration_ms = float(cleaned_event.get("duration_ms", 50.0))
            end_dt = start_dt + timedelta(milliseconds=duration_ms)

            # Check if this action represents explicit human intervention
            is_hitl = False
            hitl_action_type = None
            hitl_method = None

            if action_type in (
                BrowserActionType.APPROVAL_MODAL_CONFIRM.value,
                BrowserActionType.APPROVAL_MODAL_REJECT.value,
            ) or cleaned_event.get("human_override") or cleaned_event.get("is_human_intervention"):
                is_hitl = True
                hitl_action_type = f"browser_user_{action_type}"
                hitl_method = "OBSERVED_TELEMETRY"
                human_modals_observed += 1

            status_code = "ERROR" if action_type == BrowserActionType.APPROVAL_MODAL_REJECT.value else "OK"
            event_trace_id = cleaned_event.get("trace_id") or top_trace_id
            tool_call_id = cleaned_event.get("tool_call_id")

            span = NormalizedSpan(
                span_id=f"browser-span-{action_id}",
                trace_id=event_trace_id,
                name=f"browser_action::{action_type}",
                span_kind="INTERNAL",
                start_time=start_dt,
                end_time=end_dt,
                duration_ms=duration_ms,
                status_code=status_code,
                tool_name=selector if action_type == BrowserActionType.TOOL_TRIGGER.value else None,
                tool_call_id=tool_call_id,
                is_human_intervention=is_hitl,
                human_action_type=hitl_action_type,
                intervention_detection_method=hitl_method,
                epistemic_tag=EpistemicTag.OBSERVED,
                trust_level=effective_trust,
                normalization_version=NormalizationVersion.V1_28_0.value,
                raw_attributes={
                    "browser.action_type": action_type,
                    "browser.target_selector": selector,
                    "browser.url": cleaned_event.get("url", ""),
                    "provenance_hash": payload_hash,
                },
            )
            normalized_spans.append(span)

        envelope = self.create_provenance_envelope(
            raw_bytes=raw_bytes,
            content_type=content_type,
            provenance_hash=payload_hash,
            trust_level=effective_trust,
            redacted_fields=sorted(list(set(redacted_fields))),
            custom_metadata={
                "company_id": company_id,
                "total_browser_actions": len(normalized_spans),
                "human_modals_observed": human_modals_observed,
            },
        )

        return envelope, normalized_spans

