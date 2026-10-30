"""
Evidence-Adapter Base Contracts & Provenance Envelopes (Phase 5).

Defines the universal evidence adapter contract conforming to
docs/phase-5/evidence-adapter-architecture.md:
- AdapterCapability enumeration
- ProvenanceEnvelope dataclass with canonical serialization
- BaseEvidenceAdapter abstract interface
"""

import abc
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.ingestion.schema import NormalizedSpan
from app.epistemic.tags import TrustLevel, EpistemicTag


class AdapterCapability(str, Enum):
    """
    Certified observational capabilities declared by an evidence adapter.
    """
    CAN_OBSERVE_TOOL_CALL = "can_observe_tool_call"
    CAN_OBSERVE_TOOL_EXECUTION_RESULT = "can_observe_tool_execution_result"
    CAN_OBSERVE_HUMAN_INTERVENTION = "can_observe_human_intervention"
    CAN_OBSERVE_TOKEN_USAGE = "can_observe_token_usage"
    CAN_OBSERVE_COST = "can_observe_cost"
    CAN_OBSERVE_MODEL_IDENTITY = "can_observe_model_identity"
    CAN_OBSERVE_SERVER_SIDE_ERRORS = "can_observe_server_side_errors"


@dataclass(frozen=True)
class ProvenanceEnvelope:
    """
    Cryptographic and evidentiary provenance wrapper for ingested telemetry batches.
    Conforms to Phase 5 Architecture Specification.
    """
    adapter_id: str
    adapter_version: str
    source_framework: str
    source_version: str
    payload_sha256: str
    byte_size: int
    content_type: str
    ingested_at_utc: datetime
    epistemic_trust_level: TrustLevel
    capabilities: List[AdapterCapability]
    known_blind_spots: List[str]
    redacted_fields: List[str] = field(default_factory=list)
    custom_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converts envelope to a JSON-serializable dictionary."""
        return {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "source_framework": self.source_framework,
            "source_version": self.source_version,
            "payload_sha256": self.payload_sha256,
            "byte_size": self.byte_size,
            "content_type": self.content_type,
            "ingested_at_utc": self.ingested_at_utc.isoformat(),
            "epistemic_trust_level": self.epistemic_trust_level.value if isinstance(self.epistemic_trust_level, TrustLevel) else str(self.epistemic_trust_level),
            "capabilities": [
                c.value if isinstance(c, AdapterCapability) else str(c)
                for c in self.capabilities
            ],
            "known_blind_spots": list(self.known_blind_spots),
            "redacted_fields": list(self.redacted_fields),
            "custom_metadata": dict(self.custom_metadata),
        }

    def to_canonical_json(self, pretty: bool = False) -> str:
        """
        Deterministic canonical JSON representation conforming to RFC 8785:
        - Sorted keys
        - UTF-8 compatible
        - Strict separators
        """
        indent = 2 if pretty else None
        separators = (',', ': ') if pretty else (',', ':')
        data = self.to_dict()
        return json.dumps(
            data,
            sort_keys=True,
            indent=indent,
            separators=separators,
            ensure_ascii=False,
            default=str,
        )

    def compute_envelope_hash(self) -> str:
        """Computes SHA-256 digest of the canonical JSON envelope."""
        canonical_bytes = self.to_canonical_json(pretty=False).encode("utf-8")
        return hashlib.sha256(canonical_bytes).hexdigest()


class BaseEvidenceAdapter(abc.ABC):
    """
    Abstract contract for all evidence adapters.
    Adapters convert raw source payloads into a ProvenanceEnvelope and canonical NormalizedSpans.
    Negative invariant: Adapters must NEVER compute summary metrics, autonomy ratios,
    or verification verdicts. They solely normalize raw observations.
    """
    adapter_id: str = "base_adapter"
    adapter_version: str = "1.0.0"
    source_framework: str = "generic"
    source_version: str = "unknown"
    default_trust_level: TrustLevel = TrustLevel.T1

    @abc.abstractmethod
    def declared_capabilities(self) -> List[AdapterCapability]:
        """Returns the list of capabilities this adapter is certified to observe."""
        raise NotImplementedError

    @abc.abstractmethod
    def known_blind_spots(self) -> List[str]:
        """Returns limitations and unobservable regions for this adapter."""
        raise NotImplementedError

    @abc.abstractmethod
    def validate_payload(self, raw_bytes: bytes, content_type: str) -> Any:
        """
        Validates payload boundaries, media type, and syntax.
        Raises IngestionError, PayloadTooLargeError, or UnsupportedMediaTypeError.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def parse_and_normalize(
        self,
        raw_bytes: bytes,
        content_type: str = "application/json",
        company_id: Optional[str] = None,
        provenance_hash: Optional[str] = None
    ) -> Tuple[ProvenanceEnvelope, List[NormalizedSpan]]:
        """
        Parses raw payload, applies semantic normalization, and emits
        a ProvenanceEnvelope and canonical NormalizedSpan objects.
        """
        raise NotImplementedError

    @staticmethod
    def compute_sha256(raw_bytes: bytes) -> str:
        """Computes canonical SHA-256 digest of exact raw payload bytes before parsing."""
        return hashlib.sha256(raw_bytes).hexdigest()

    def create_provenance_envelope(
        self,
        raw_bytes: bytes,
        content_type: str,
        provenance_hash: Optional[str] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
        redacted_fields: Optional[List[str]] = None,
        trust_level: Optional[TrustLevel] = None,
    ) -> ProvenanceEnvelope:
        """Builds a standardized ProvenanceEnvelope for this adapter."""
        sha256 = provenance_hash or self.compute_sha256(raw_bytes)
        return ProvenanceEnvelope(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            source_framework=self.source_framework,
            source_version=self.source_version,
            payload_sha256=sha256,
            byte_size=len(raw_bytes),
            content_type=content_type,
            ingested_at_utc=datetime.now(timezone.utc),
            epistemic_trust_level=trust_level or self.default_trust_level,
            capabilities=self.declared_capabilities(),
            known_blind_spots=self.known_blind_spots(),
            redacted_fields=redacted_fields or [],
            custom_metadata=custom_metadata or {},
        )
