"""
Unit Tests for Versioned Semantic Normalizer.
Validates OpenTelemetry GenAI v1.28.0 attributes, legacy aliases, conflict resolution,
zero-token vs absent-token handling, and unmapped attribute preservation.
"""

import pytest
from datetime import datetime
from app.ingestion.normalizer import (
    normalize_span_payload,
    flatten_otlp_attributes,
    extract_otlp_attribute_value,
    SUPPORTED_CONVENTION_VERSION
)
from app.ingestion.schema import NormalizedSpan, NormalizationVersion
from app.epistemic.tags import EpistemicTag, TrustLevel

def test_flatten_otlp_attributes_list():
    raw_list = [
        {"key": "gen_ai.system", "value": {"stringValue": "openai"}},
        {"key": "gen_ai.usage.prompt_tokens", "value": {"intValue": 500}},
        {"key": "is_active", "value": {"boolValue": True}},
        {"key": "temperature", "value": {"doubleValue": 0.7}}
    ]
    flattened = flatten_otlp_attributes(raw_list)
    assert flattened["gen_ai.system"] == "openai"
    assert flattened["gen_ai.usage.prompt_tokens"] == 500
    assert flattened["is_active"] is True
    assert flattened["temperature"] == 0.7

def test_flatten_otlp_attributes_dict():
    raw_dict = {
        "gen_ai.provider.name": "anthropic",
        "gen_ai.usage.input_tokens": 1200
    }
    flattened = flatten_otlp_attributes(raw_dict)
    assert flattened["gen_ai.provider.name"] == "anthropic"
    assert flattened["gen_ai.usage.input_tokens"] == 1200

def test_normalize_modern_genai_attributes():
    raw_span = {
        "traceId": "11112222333344445555666677778888",
        "spanId": "aaaabbbbccccdddd",
        "name": "chat_completion",
        "kind": "INTERNAL",
        "startTimeUnixNano": "1726999200000000000",
        "endTimeUnixNano": "1726999201500000000",
        "attributes": {
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.response.model": "gpt-4o-2024-08-06",
            "gen_ai.operation.name": "chat",
            "gen_ai.usage.input_tokens": 400,
            "gen_ai.usage.output_tokens": 150
        }
    }
    normalized = normalize_span_payload(raw_span)
    assert normalized.trace_id == "11112222333344445555666677778888"
    assert normalized.span_id == "aaaabbbbccccdddd"
    assert normalized.provider_name == "openai"
    assert normalized.requested_model == "gpt-4o"
    assert normalized.response_model == "gpt-4o-2024-08-06"
    assert normalized.operation_name == "chat"
    assert normalized.input_tokens == 400
    assert normalized.output_tokens == 150
    assert normalized.has_token_data is True
    assert normalized.duration_ms == 1500.0
    assert normalized.cost_usd > 0
    assert normalized.normalization_version == NormalizationVersion.V1_28_0.value

def test_normalize_legacy_aliases():
    raw_span = {
        "trace_id": "legacy_trace_123",
        "span_id": "legacy_span_456",
        "name": "generate",
        "attributes": {
            "gen_ai.system": "anthropic",
            "model_name": "claude-3-5-sonnet",
            "prompt_tokens": 300,
            "completion_tokens": 80
        }
    }
    normalized = normalize_span_payload(raw_span)
    assert normalized.provider_name == "anthropic"
    assert normalized.requested_model == "claude-3-5-sonnet"
    assert normalized.input_tokens == 300
    assert normalized.output_tokens == 80
    assert normalized.has_token_data is True

def test_normalize_conflicting_aliases_resolution():
    # Both modern and legacy present with differing values: modern must win and conflict must be logged
    raw_span = {
        "trace_id": "conflict_trace",
        "span_id": "conflict_span",
        "name": "chat",
        "attributes": {
            "gen_ai.provider.name": "openai",
            "gen_ai.system": "custom_openai_wrapper",
            "gen_ai.usage.input_tokens": 600,
            "gen_ai.usage.prompt_tokens": 550
        }
    }
    normalized = normalize_span_payload(raw_span)
    # Selected values
    assert normalized.provider_name == "openai"
    assert normalized.input_tokens == 600
    # Conflict records
    assert "provider_name" in normalized.conflicts
    assert normalized.conflicts["provider_name"]["selected"] == "openai"
    assert normalized.conflicts["provider_name"]["conflicting"] == "custom_openai_wrapper"
    assert "input_tokens" in normalized.conflicts

def test_normalize_zero_vs_absent_tokens():
    # Zero tokens present
    span_with_zero = {
        "trace_id": "zero_trace",
        "span_id": "zero_span",
        "name": "cached_call",
        "attributes": {
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.usage.input_tokens": 0,
            "gen_ai.usage.output_tokens": 0
        }
    }
    norm_zero = normalize_span_payload(span_with_zero)
    assert norm_zero.input_tokens == 0
    assert norm_zero.output_tokens == 0
    assert norm_zero.has_token_data is True
    assert "input_tokens" not in norm_zero.missing_fields

    # Tokens completely absent
    span_no_tokens = {
        "trace_id": "none_trace",
        "span_id": "none_span",
        "name": "non_llm_span",
        "attributes": {
            "custom.event": "user_click"
        }
    }
    norm_none = normalize_span_payload(span_no_tokens)
    assert norm_none.input_tokens is None
    assert norm_none.output_tokens is None
    assert norm_none.has_token_data is False
    assert "input_tokens" in norm_none.missing_fields
    assert "output_tokens" in norm_none.missing_fields

def test_normalize_preserves_unmapped_attributes():
    raw_span = {
        "trace_id": "unmapped_trace",
        "span_id": "unmapped_span",
        "name": "custom_agent_step",
        "attributes": {
            "gen_ai.provider.name": "openai",
            "gen_ai.request.model": "gpt-4o",
            "agent.custom_metric": 42,
            "environment.zone": "us-east-1",
            "user.id": "user_992"
        }
    }
    normalized = normalize_span_payload(raw_span)
    assert normalized.unmapped_attributes["agent.custom_metric"] == 42
    assert normalized.unmapped_attributes["environment.zone"] == "us-east-1"
    assert normalized.unmapped_attributes["user.id"] == "user_992"

def test_normalize_deterministic_across_runs():
    raw_span = {
        "traceId": "det_trace_999",
        "spanId": "det_span_999",
        "name": "deterministic_test",
        "attributes": {
            "gen_ai.provider.name": "anthropic",
            "gen_ai.request.model": "claude-3-5-sonnet",
            "gen_ai.usage.input_tokens": 800,
            "gen_ai.usage.output_tokens": 200
        }
    }
    norm1 = normalize_span_payload(raw_span).to_dict()
    norm2 = normalize_span_payload(raw_span).to_dict()
    assert norm1 == norm2
