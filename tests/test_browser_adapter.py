"""
Phase 5 Milestone E Tests: Browser Action Telemetry Adapter & Privacy Constraints.

Validates WebExtension event normalization, sensitive credential redaction,
DOM stripping, and human approval modal intervention mapping.
"""

import json
import pytest

from app.adapters.browser import BrowserEvidenceAdapter, BrowserActionType
from app.adapters.base import AdapterCapability
from app.epistemic.tags import TrustLevel
from app.analysis.task_segmentation import segment_trace, TaskOutcome
from app.ingestion.otlp_handler import (
    IngestionError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)


@pytest.fixture
def browser_adapter():
    return BrowserEvidenceAdapter()


def test_browser_adapter_capabilities_and_metadata(browser_adapter):
    """BrowserEvidenceAdapter declares expected T1 trust and privacy boundary disclosures."""
    assert browser_adapter.adapter_id == "browser_action_adapter"
    assert browser_adapter.adapter_version == "1.0.0"
    assert browser_adapter.source_framework == "web_extension"
    assert browser_adapter.default_trust_level == TrustLevel.T1

    caps = browser_adapter.declared_capabilities()
    assert AdapterCapability.CAN_OBSERVE_HUMAN_INTERVENTION in caps
    assert AdapterCapability.CAN_OBSERVE_TOOL_CALL in caps
    assert AdapterCapability.CAN_OBSERVE_TOOL_EXECUTION_RESULT in caps

    blind_spots = browser_adapter.known_blind_spots()
    assert any("server-side llm prompts" in s.lower() for s in blind_spots)


def test_browser_adapter_payload_validation(browser_adapter):
    """Payload boundaries and media types are strictly enforced."""
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    with pytest.raises(PayloadTooLargeError):
        browser_adapter.validate_payload(oversized)

    with pytest.raises(UnsupportedMediaTypeError):
        browser_adapter.validate_payload(b"{}", "text/html")

    with pytest.raises(IngestionError):
        browser_adapter.validate_payload(b"{bad-json")

    with pytest.raises(IngestionError):
        browser_adapter.parse_and_normalize(b'{"actions": []}')


def test_browser_adapter_privacy_redaction_and_dom_stripping(browser_adapter):
    """DOM trees, credit cards, passwords, and API keys are scrubbed from telemetry."""
    payload = {
        "trace_id": "browser-priv-001",
        "actions": [
            {
                "action_type": BrowserActionType.INPUT_TEXT.value,
                "action_id": "act-1",
                "target_selector": "input#card-number",
                "input_value": "4111 2222 3333 4444",
                "dom_tree": "<div><form>Full DOM Dump</form></div>",
                "outer_html": "<input id='card-number' />",
            },
            {
                "action_type": BrowserActionType.INPUT_TEXT.value,
                "action_id": "act-2",
                "target_selector": "input#pwd",
                "is_password_field": True,
                "input_value": "mySecretPassword123!",
            },
            {
                "action_type": BrowserActionType.INPUT_TEXT.value,
                "action_id": "act-3",
                "target_selector": "input#api-key",
                "input_value": "Bearer sk-1234567890abcdef1234567890abcdef",
            }
        ]
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    envelope, spans = browser_adapter.parse_and_normalize(raw_bytes)

    assert len(spans) == 3

    # Redacted fields reported in envelope
    assert "dom_tree" in envelope.redacted_fields
    assert "outer_html" in envelope.redacted_fields
    assert "input_value" in envelope.redacted_fields

    # Confirm raw_attributes do not contain raw DOM or unscrubbed secrets
    for s in spans:
        raw_attrs = s.raw_attributes
        assert "dom_tree" not in raw_attrs
        assert "outer_html" not in raw_attrs
        assert "4111" not in str(raw_attrs)
        assert "mySecretPassword" not in str(raw_attrs)
        assert "sk-123456" not in str(raw_attrs)


def test_browser_adapter_approval_modal_human_intervention(browser_adapter):
    """User approval modal clicks map to explicit human intervention (OBSERVED_TELEMETRY)."""
    payload = {
        "trace_id": "trace-approval-flow-01",
        "actions": [
            {
                "action_type": BrowserActionType.CLICK.value,
                "action_id": "act-nav",
                "target_selector": "button#submit-transfer",
                "timestamp": "2026-10-23T10:00:00Z",
                "duration_ms": 30.0,
            },
            {
                "action_type": BrowserActionType.APPROVAL_MODAL_CONFIRM.value,
                "action_id": "act-approve",
                "target_selector": "button#confirm-high-value-wire",
                "timestamp": "2026-10-23T10:00:02Z",
                "duration_ms": 100.0,
            }
        ]
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    envelope, spans = browser_adapter.parse_and_normalize(raw_bytes)

    assert len(spans) == 2
    assert envelope.custom_metadata["human_modals_observed"] == 1

    # Span 1: Normal action
    assert spans[0].is_human_intervention is False

    # Span 2: Human approval modal
    approval_span = spans[1]
    assert approval_span.is_human_intervention is True
    assert approval_span.intervention_detection_method == "OBSERVED_TELEMETRY"
    assert "approval_modal_confirm" in approval_span.human_action_type

    # Segment the trace: should be classified as HUMAN_EXPLICIT
    seg = segment_trace(spans, trace_id="trace-approval-flow-01")
    assert any(t.outcome == TaskOutcome.HUMAN_EXPLICIT for t in seg.tasks)
    assert seg.human_explicit_count >= 1
    assert seg.autonomy.bounds.point_estimate < 100.0

