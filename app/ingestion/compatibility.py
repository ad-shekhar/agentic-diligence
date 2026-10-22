"""
Integration Compatibility Matrix for OpenTelemetry Agent Frameworks and Exporters.
Documents tested versions, observed telemetry attributes, mapping decisions,
and known limitations.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

@dataclass
class CompatibilityRecord:
    framework: str
    tested_version: str
    exporter_type: str
    supported_format: str
    observed_attributes: List[str]
    mapped_fields: List[str]
    unsupported_fields: List[str]
    notes: str
    epistemic_level: str = "T1"

# Official Phase 2 Integration Compatibility Matrix
INTEGRATION_MATRIX: Dict[str, CompatibilityRecord] = {
    "langchain_opentelemetry": CompatibilityRecord(
        framework="LangChain / LangGraph",
        tested_version="0.2.x / 0.1.x",
        exporter_type="OTLP HTTP/JSON (OpenTelemetry SDK)",
        supported_format="resourceSpans JSON & Flattened Dict",
        observed_attributes=[
            "gen_ai.system", "gen_ai.request.model", "gen_ai.usage.prompt_tokens",
            "gen_ai.usage.completion_tokens", "gen_ai.operation.name", "llm.provider",
            "langchain.run_id", "langchain.parent_run_id"
        ],
        mapped_fields=[
            "provider_name", "requested_model", "input_tokens",
            "output_tokens", "operation_name"
        ],
        unsupported_fields=[
            "gen_ai.response.model (often omitted in streaming)",
            "precise token cache read/write stats (provider dependent)"
        ],
        notes="Standard LangChain OpenTelemetry exporter emits v1.26-style gen_ai.system and prompt_tokens.",
        epistemic_level="T1"
    ),
    "claude_mcp_observer": CompatibilityRecord(
        framework="Claude Desktop / MCP Stdio Observer",
        tested_version="MCP Protocol 2024-11-05",
        exporter_type="OTLP HTTP/JSON (agd-proxy / stdio)",
        supported_format="OTLP Standard JSON (resourceSpans)",
        observed_attributes=[
            "gen_ai.provider.name", "gen_ai.request.model", "gen_ai.tool.name",
            "gen_ai.tool.call_id", "gen_ai.tool.status", "mcp.method", "mcp.protocol_version"
        ],
        mapped_fields=[
            "provider_name", "requested_model", "tool_name", "tool_call_id", "tool_status"
        ],
        unsupported_fields=[
            "internal prompt thought tokens (private agent reasoning hidden inside client)"
        ],
        notes="MCP tool executions captured with sub-millisecond precision. Tool calls map to T2 independent proxy level when captured via agd-proxy.",
        epistemic_level="T2"
    ),
    "crewai_opentelemetry": CompatibilityRecord(
        framework="CrewAI Hierarchical Agent",
        tested_version="0.30.x+",
        exporter_type="OTLP HTTP/JSON",
        supported_format="resourceSpans JSON",
        observed_attributes=[
            "gen_ai.system", "model_name", "prompt_tokens", "completion_tokens",
            "agent.role", "agent.goal", "task.description"
        ],
        mapped_fields=[
            "provider_name", "requested_model", "input_tokens", "output_tokens"
        ],
        unsupported_fields=[
            "per-step evaluator cost overhead (aggregated at crew level)"
        ],
        notes="CrewAI uses framework-level aliases model_name and prompt_tokens alongside OTel conventions.",
        epistemic_level="T1"
    ),
    "standard_otlp_collector": CompatibilityRecord(
        framework="OpenTelemetry Collector / GenAI Exporter",
        tested_version="v0.98.0+ / GenAI v1.28.0",
        exporter_type="OTLP HTTP/JSON POST /v1/traces",
        supported_format="Full OTLP Protobuf-JSON Envelope",
        observed_attributes=[
            "gen_ai.provider.name", "gen_ai.request.model", "gen_ai.response.model",
            "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens", "gen_ai.operation.name"
        ],
        mapped_fields=[
            "provider_name", "requested_model", "response_model", "input_tokens",
            "output_tokens", "operation_name"
        ],
        unsupported_fields=[
            "Protobuf binary format (deferred; OTLP HTTP/JSON fully supported)"
        ],
        notes="Direct standards-compliant ingestion on /v1/traces with SHA-256 provenance.",
        epistemic_level="T1"
    )
}

def get_compatibility_matrix() -> Dict[str, Dict[str, Any]]:
    """Returns matrix as dictionary for API or documentation export."""
    return {
        key: {
            "framework": rec.framework,
            "tested_version": rec.tested_version,
            "exporter_type": rec.exporter_type,
            "supported_format": rec.supported_format,
            "observed_attributes": rec.observed_attributes,
            "mapped_fields": rec.mapped_fields,
            "unsupported_fields": rec.unsupported_fields,
            "notes": rec.notes,
            "epistemic_level": rec.epistemic_level
        }
        for key, rec in INTEGRATION_MATRIX.items()
    }
