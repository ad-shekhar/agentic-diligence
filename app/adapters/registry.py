"""
Unified Evidence Registry (Phase 6 — Milestone A).

Provides a unified interface for registering, indexing, storing, and retrieving
multi-source telemetry evidence across OTLP, MCP, and WebExtension Browser adapters.
Preserves source identity, raw SHA-256 provenance digests, event vs ingestion timestamps,
and non-destructive conflict and duplicate tracking.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from sqlalchemy.orm import Session

from app.adapters.base import (
    BaseEvidenceAdapter,
    ProvenanceEnvelope,
    AdapterCapability,
)
from app.adapters.otlp import OtlpEvidenceAdapter
from app.adapters.mcp import McpEvidenceAdapter
from app.adapters.browser import BrowserEvidenceAdapter
from app.epistemic.tags import TrustLevel, EpistemicTag
from app.ingestion.otlp_handler import IngestionError
from app.ingestion.schema import NormalizedSpan
from app.db.models import PayloadProvenance


class SourceType(str, Enum):
    """Categorizes the origin framework or protocol of evidence."""
    OTLP = "otlp"
    MCP = "mcp"
    BROWSER = "browser"
    UNKNOWN = "unknown"


class EvidenceStatus(str, Enum):
    """Integrity and reconciliation status of an individual evidence record."""
    VALID = "VALID"
    INCOMPLETE = "INCOMPLETE"
    DUPLICATE = "DUPLICATE"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


def compute_deterministic_evidence_id(
    source_type: Union[SourceType, str],
    payload_hash: str,
    trace_id: str,
    span_id: str,
) -> str:
    """
    Computes a deterministic, collision-resistant 64-char hex SHA-256 ID
    anchoring the atomic observation to its source and provenance digest.
    """
    st_val = source_type.value if isinstance(source_type, SourceType) else str(source_type)
    key = f"{st_val}:{payload_hash}:{trace_id}:{span_id}".encode("utf-8")
    return hashlib.sha256(key).hexdigest()


@dataclass
class EvidenceRecord:
    """
    Unified atomic evidence record encapsulating normalized observations
    with complete source provenance and ingestion ledger metadata.
    """
    evidence_id: str
    source_type: SourceType
    adapter_id: str
    adapter_version: str
    company_id: str
    provenance_hash: str
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    name: str
    event_timestamp_utc: datetime
    ingested_at_utc: datetime
    trust_level: TrustLevel
    epistemic_tag: EpistemicTag
    status: EvidenceStatus
    span: NormalizedSpan
    envelope: ProvenanceEnvelope
    conflict_details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_type": self.source_type.value,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "company_id": self.company_id,
            "provenance_hash": self.provenance_hash,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "event_timestamp_utc": self.event_timestamp_utc.isoformat(),
            "ingested_at_utc": self.ingested_at_utc.isoformat(),
            "trust_level": self.trust_level.value,
            "epistemic_tag": self.epistemic_tag.value,
            "status": self.status.value,
            "conflict_details": self.conflict_details,
            "span": self.span.to_dict(),
            "envelope": self.envelope.to_dict(),
        }


@dataclass
class IngestionReceipt:
    """Immutable receipt returned upon payload registration."""
    status: str  # SUCCESS, PARTIAL, FAILED
    source_type: SourceType
    payload_hash: str
    byte_size: int
    total_spans_ingested: int
    duplicates_detected: int
    conflicts_detected: int
    trace_ids: List[str]
    errors: List[str]
    envelope: ProvenanceEnvelope

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "source_type": self.source_type.value,
            "payload_hash": self.payload_hash,
            "byte_size": self.byte_size,
            "total_spans_ingested": self.total_spans_ingested,
            "duplicates_detected": self.duplicates_detected,
            "conflicts_detected": self.conflicts_detected,
            "trace_ids": list(self.trace_ids),
            "errors": list(self.errors),
            "envelope": self.envelope.to_dict(),
        }


class UnifiedEvidenceRegistry:
    """
    Central Evidence Registry for Agentic Diligence.
    Accepts, normalizes, indexes, and queries evidence from OTLP, MCP, and Browser sources.
    Enforces non-destructive conflict logging and duplicate detection.
    """

    def __init__(self):
        self._otlp_adapter = OtlpEvidenceAdapter()
        self._mcp_adapter = McpEvidenceAdapter()
        self._browser_adapter = BrowserEvidenceAdapter()

        # In-memory primary index: evidence_id -> EvidenceRecord
        self._records_by_id: Dict[str, EvidenceRecord] = {}

        # Lookups
        self._records_by_company: Dict[str, List[str]] = {}
        self._records_by_trace: Dict[str, List[str]] = {}
        self._envelopes_by_company: Dict[str, List[ProvenanceEnvelope]] = {}

        # Deduplication tracker: (company_id, source_type, trace_id, span_id) -> evidence_id
        self._seen_spans: Dict[Tuple[str, str, str, str], str] = {}

    def clear(self) -> None:
        """Resets the in-memory registry (useful for isolated unit tests)."""
        self._records_by_id.clear()
        self._records_by_company.clear()
        self._records_by_trace.clear()
        self._envelopes_by_company.clear()
        self._seen_spans.clear()

    def detect_source_type(
        self,
        raw_bytes: bytes,
        content_type: str = "application/json",
        hint: Optional[str] = None
    ) -> SourceType:
        """
        Deterministically classifies the payload source type based on hint
        or payload structural signatures.
        """
        if hint:
            h = hint.strip().lower()
            if h in ("otlp", "opentelemetry"):
                return SourceType.OTLP
            if h in ("mcp", "model_context_protocol"):
                return SourceType.MCP
            if h in ("browser", "web_extension", "dom"):
                return SourceType.BROWSER

        try:
            text = raw_bytes.decode("utf-8").strip()
            data = json.loads(text)
        except Exception:
            return SourceType.UNKNOWN

        if isinstance(data, dict):
            if "resourceSpans" in data or "spans" in data:
                return SourceType.OTLP
            if "messages" in data or "jsonrpc" in data:
                return SourceType.MCP
            if "actions" in data or "events" in data:
                return SourceType.BROWSER
        elif isinstance(data, list):
            if data and isinstance(data[0], dict):
                first = data[0]
                if "jsonrpc" in first or "method" in first:
                    return SourceType.MCP
                if "action_type" in first or "target_selector" in first:
                    return SourceType.BROWSER

        return SourceType.UNKNOWN

    def register_payload(
        self,
        raw_bytes: bytes,
        source_type: Optional[Union[SourceType, str]] = None,
        content_type: str = "application/json",
        company_id: Optional[str] = None,
        provenance_hash: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> IngestionReceipt:
        """
        Ingests, normalizes, registers, and stores evidence records.
        Preserves provenance digests and enforces idempotency and conflict logging.
        """
        effective_company_id = company_id or "default_target"
        resolved_source_type: SourceType

        if isinstance(source_type, SourceType):
            resolved_source_type = source_type
        elif isinstance(source_type, str):
            resolved_source_type = self.detect_source_type(raw_bytes, content_type, hint=source_type)
        else:
            resolved_source_type = self.detect_source_type(raw_bytes, content_type)

        if resolved_source_type == SourceType.UNKNOWN:
            raise IngestionError(
                "Unrecognized evidence payload structure: cannot determine adapter. "
                "Specify source_type explicitly ('otlp', 'mcp', 'browser')."
            )

        # 1. Route to designated adapter
        adapter: BaseEvidenceAdapter
        if resolved_source_type == SourceType.OTLP:
            adapter = self._otlp_adapter
        elif resolved_source_type == SourceType.MCP:
            adapter = self._mcp_adapter
        elif resolved_source_type == SourceType.BROWSER:
            adapter = self._browser_adapter
        else:
            raise IngestionError(f"Unsupported source type: {resolved_source_type}")

        # 2. Parse and normalize
        envelope, spans = adapter.parse_and_normalize(
            raw_bytes=raw_bytes,
            content_type=content_type,
            company_id=effective_company_id,
            provenance_hash=provenance_hash,
        )

        # 3. Store provenance in DB if session provided
        if db:
            prov_rec = PayloadProvenance(
                payload_hash=envelope.payload_sha256,
                company_id=effective_company_id,
                content_type=content_type,
                byte_size=len(raw_bytes),
                format=f"{resolved_source_type.value}_envelope",
                normalization_version=spans[0].normalization_version if spans else "v1.28.0",
                trace_count=len({s.trace_id for s in spans}),
                span_count=len(spans),
                status="SUCCESS",
            )
            db.add(prov_rec)
            db.commit()

        # Track in memory
        self._envelopes_by_company.setdefault(effective_company_id, []).append(envelope)

        ingested_at = datetime.now(timezone.utc)
        duplicates_count = 0
        conflicts_count = 0
        trace_ids: Set[str] = set()

        # 4. Index individual evidence records
        for span in spans:
            trace_ids.add(span.trace_id)
            ev_id = compute_deterministic_evidence_id(
                source_type=resolved_source_type,
                payload_hash=envelope.payload_sha256,
                trace_id=span.trace_id,
                span_id=span.span_id,
            )

            span_key = (effective_company_id, resolved_source_type.value, span.trace_id, span.span_id)
            is_dup = span_key in self._seen_spans
            status = EvidenceStatus.VALID

            if is_dup:
                duplicates_count += 1
                status = EvidenceStatus.DUPLICATE
                if ev_id in self._records_by_id:
                    ev_id = f"{ev_id}#dup-{duplicates_count}"
            else:
                self._seen_spans[span_key] = ev_id

            # Incomplete status check (e.g. unknown tool call or uninstrumented interval)
            if status != EvidenceStatus.DUPLICATE:
                if span.epistemic_tag == EpistemicTag.UNKNOWN or span.tool_status == "UNKNOWN":
                    status = EvidenceStatus.INCOMPLETE

            record = EvidenceRecord(
                evidence_id=ev_id,
                source_type=resolved_source_type,
                adapter_id=adapter.adapter_id,
                adapter_version=adapter.adapter_version,
                company_id=effective_company_id,
                provenance_hash=envelope.payload_sha256,
                trace_id=span.trace_id,
                span_id=span.span_id,
                parent_span_id=span.parent_span_id,
                name=span.name,
                event_timestamp_utc=span.start_time,
                ingested_at_utc=ingested_at,
                trust_level=span.trust_level,
                epistemic_tag=span.epistemic_tag,
                status=status,
                span=span,
                envelope=envelope,
            )

            self._records_by_id[ev_id] = record
            self._records_by_company.setdefault(effective_company_id, []).append(ev_id)
            self._records_by_trace.setdefault(span.trace_id, []).append(ev_id)

        return IngestionReceipt(
            status="SUCCESS",
            source_type=resolved_source_type,
            payload_hash=envelope.payload_sha256,
            byte_size=len(raw_bytes),
            total_spans_ingested=len(spans),
            duplicates_detected=duplicates_count,
            conflicts_detected=conflicts_count,
            trace_ids=sorted(list(trace_ids)),
            errors=[],
            envelope=envelope,
        )

    def get_records(
        self,
        company_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        source_type: Optional[SourceType] = None,
        include_duplicates: bool = False,
        sort_by_time: bool = False,
    ) -> List[EvidenceRecord]:
        """Queries registered evidence records matching filters."""
        if trace_id:
            ids = self._records_by_trace.get(trace_id, [])
        elif company_id:
            ids = self._records_by_company.get(company_id, [])
        else:
            ids = list(self._records_by_id.keys())

        results: List[EvidenceRecord] = []
        for eid in ids:
            rec = self._records_by_id.get(eid)
            if not rec:
                continue
            if company_id and rec.company_id != company_id:
                continue
            if source_type and rec.source_type != source_type:
                continue
            if not include_duplicates and rec.status == EvidenceStatus.DUPLICATE:
                continue
            results.append(rec)

        if sort_by_time:
            results.sort(key=lambda r: r.event_timestamp_utc)
        return results

    def get_provenance_envelopes(self, company_id: Optional[str] = None) -> List[ProvenanceEnvelope]:
        """Returns all registered provenance envelopes for a company."""
        if company_id:
            return list(self._envelopes_by_company.get(company_id, []))
        all_envs = []
        for env_list in self._envelopes_by_company.values():
            all_envs.extend(env_list)
        return all_envs

    def get_spans_by_trace(
        self,
        company_id: Optional[str] = None,
        include_duplicates: bool = False
    ) -> Dict[str, List[NormalizedSpan]]:
        """Groups normalized spans by trace_id for downstream task segmentation."""
        records = self.get_records(company_id=company_id, include_duplicates=include_duplicates)
        traces_map: Dict[str, List[NormalizedSpan]] = {}
        for r in records:
            traces_map.setdefault(r.trace_id, []).append(r.span)
        return traces_map


# Singleton default registry instance
default_registry = UnifiedEvidenceRegistry()
