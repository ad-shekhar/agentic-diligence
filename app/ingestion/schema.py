"""
Canonical Data Model for Normalized OpenTelemetry GenAI Telemetry.
Preserves raw source evidence, source provenance, normalization decisions,
epistemic tagging, and explicit missing/unsupported fields.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional
from app.epistemic.tags import EpistemicTag, TrustLevel

class NormalizationVersion(str, Enum):
    V1_28_0 = "v1.28.0"
    LEGACY = "legacy_compat"

@dataclass
class NormalizedSpan:
    """
    Canonical representation of a single span across arbitrary OTel agent frameworks.
    """
    span_id: str
    trace_id: str
    name: str
    span_kind: str  # internal, server, client, producer, consumer, or agent/tool/llm
    start_time: datetime
    end_time: datetime
    duration_ms: float
    status_code: str  # UNSET, OK, ERROR
    status_message: Optional[str] = None
    parent_span_id: Optional[str] = None

    # GenAI Semantic Conventions (v1.28.0)
    provider_name: Optional[str] = None
    requested_model: Optional[str] = None
    response_model: Optional[str] = None
    operation_name: Optional[str] = None  # chat, text_completion, embeddings, execute_tool

    # Token Usage: Distinguish 0 from None (absent)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    has_token_data: bool = False

    # Tool Metadata
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_status: Optional[str] = None

    # Human Intervention
    is_human_intervention: bool = False
    human_action_type: Optional[str] = None
    intervention_detection_method: Optional[str] = None

    # Cost
    cost_usd: float = 0.0
    cost_status: str = "MEASURED"

    # Epistemic & Provenance Tracking
    epistemic_tag: EpistemicTag = EpistemicTag.OBSERVED
    trust_level: TrustLevel = TrustLevel.T1
    normalization_version: str = NormalizationVersion.V1_28_0.value

    # Preserved Attributes & Metadata
    unmapped_attributes: Dict[str, Any] = field(default_factory=dict)
    conflicts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    missing_fields: List[str] = field(default_factory=list)
    raw_attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "span_kind": self.span_kind,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_ms": round(self.duration_ms, 2),
            "status_code": self.status_code,
            "status_message": self.status_message,
            "provider_name": self.provider_name,
            "requested_model": self.requested_model,
            "response_model": self.response_model,
            "operation_name": self.operation_name,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "has_token_data": self.has_token_data,
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "tool_status": self.tool_status,
            "is_human_intervention": self.is_human_intervention,
            "human_action_type": self.human_action_type,
            "intervention_detection_method": self.intervention_detection_method,
            "cost_usd": round(self.cost_usd, 6),
            "cost_status": self.cost_status,
            "epistemic_tag": self.epistemic_tag.value if hasattr(self.epistemic_tag, "value") else str(self.epistemic_tag),
            "trust_level": self.trust_level.value if hasattr(self.trust_level, "value") else str(self.trust_level),
            "normalization_version": self.normalization_version,
            "unmapped_attributes": self.unmapped_attributes,
            "conflicts": self.conflicts,
            "missing_fields": self.missing_fields,
            "raw_attributes": self.raw_attributes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "NormalizedSpan":
        """Reconstructs a NormalizedSpan from a serialized dictionary."""
        st = d.get("start_time")
        if isinstance(st, str):
            start_time_dt = datetime.fromisoformat(st)
        else:
            start_time_dt = st

        et = d.get("end_time")
        if isinstance(et, str):
            end_time_dt = datetime.fromisoformat(et)
        else:
            end_time_dt = et

        ep_tag = d.get("epistemic_tag", EpistemicTag.OBSERVED)
        if isinstance(ep_tag, str):
            try:
                ep_tag = EpistemicTag(ep_tag)
            except ValueError:
                ep_tag = EpistemicTag.OBSERVED

        tr_lvl = d.get("trust_level", TrustLevel.T1)
        if isinstance(tr_lvl, str):
            try:
                tr_lvl = TrustLevel(tr_lvl)
            except ValueError:
                tr_lvl = TrustLevel.T1

        return cls(
            span_id=d.get("span_id", ""),
            trace_id=d.get("trace_id", ""),
            name=d.get("name", ""),
            span_kind=d.get("span_kind", "internal"),
            start_time=start_time_dt,
            end_time=end_time_dt,
            duration_ms=float(d.get("duration_ms", 0.0)),
            status_code=d.get("status_code", "UNSET"),
            status_message=d.get("status_message"),
            parent_span_id=d.get("parent_span_id"),
            provider_name=d.get("provider_name"),
            requested_model=d.get("requested_model"),
            response_model=d.get("response_model"),
            operation_name=d.get("operation_name"),
            input_tokens=d.get("input_tokens"),
            output_tokens=d.get("output_tokens"),
            has_token_data=bool(d.get("has_token_data", False)),
            tool_name=d.get("tool_name"),
            tool_call_id=d.get("tool_call_id"),
            tool_status=d.get("tool_status"),
            is_human_intervention=bool(d.get("is_human_intervention", False)),
            human_action_type=d.get("human_action_type"),
            intervention_detection_method=d.get("intervention_detection_method"),
            cost_usd=float(d.get("cost_usd", 0.0)),
            cost_status=d.get("cost_status", "MEASURED"),
            epistemic_tag=ep_tag,
            trust_level=tr_lvl,
            normalization_version=d.get("normalization_version", NormalizationVersion.V1_28_0.value),
            unmapped_attributes=d.get("unmapped_attributes", {}) or {},
            conflicts=d.get("conflicts", {}) or {},
            missing_fields=d.get("missing_fields", []) or [],
            raw_attributes=d.get("raw_attributes", {}) or {},
        )

@dataclass
class NormalizedTrace:
    """
    Canonical representation of a full trace composed of normalized spans.
    """
    trace_id: str
    workflow_name: str
    start_time: datetime
    end_time: datetime
    duration_ms: float
    status_code: str
    spans: List[NormalizedSpan]
    provenance_hash: str
    has_human_intervention: bool = False
    total_cost_usd: float = 0.0
    has_unpriced_model: bool = False
    missing_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "workflow_name": self.workflow_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_ms": round(self.duration_ms, 2),
            "status_code": self.status_code,
            "spans_count": len(self.spans),
            "has_human_intervention": self.has_human_intervention,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "has_unpriced_model": self.has_unpriced_model,
            "provenance_hash": self.provenance_hash,
            "spans": [s.to_dict() for s in self.spans]
        }

@dataclass
class IngestionResult:
    """
    Audit-grade ingestion response with cryptographic provenance.
    """
    status: str  # SUCCESS, PARTIAL, FAILED
    payload_hash: str
    byte_size: int
    content_type: str
    normalization_version: str
    traces_count: int
    spans_count: int
    trace_ids: List[str]
    errors: List[str] = field(default_factory=list)
    partial_success_rejected_spans: int = 0
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "payload_hash": self.payload_hash,
            "byte_size": self.byte_size,
            "content_type": self.content_type,
            "normalization_version": self.normalization_version,
            "traces_count": self.traces_count,
            "spans_count": self.spans_count,
            "trace_ids": self.trace_ids,
            "errors": self.errors,
            "partial_success": {
                "rejected_spans": self.partial_success_rejected_spans
            } if self.partial_success_rejected_spans > 0 else {},
            "duration_ms": round(self.duration_ms, 2)
        }
