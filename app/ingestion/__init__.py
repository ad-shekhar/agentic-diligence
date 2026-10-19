"""
OpenTelemetry Ingestion, Normalization, and Compatibility Package.
"""

from app.ingestion.schema import NormalizedSpan, NormalizedTrace, IngestionResult, NormalizationVersion
from app.ingestion.normalizer import (
    normalize_span_payload,
    flatten_otlp_attributes,
    extract_otlp_attribute_value,
    SUPPORTED_CONVENTION_VERSION
)
from app.ingestion.compatibility import (
    INTEGRATION_MATRIX,
    CompatibilityRecord,
    get_compatibility_matrix
)
from app.ingestion.otlp_handler import (
    process_otlp_http_bytes,
    compute_raw_payload_hash,
    IngestionError,
    UnsupportedMediaTypeError,
    PayloadTooLargeError
)

__all__ = [
    "NormalizedSpan",
    "NormalizedTrace",
    "IngestionResult",
    "NormalizationVersion",
    "normalize_span_payload",
    "flatten_otlp_attributes",
    "extract_otlp_attribute_value",
    "SUPPORTED_CONVENTION_VERSION",
    "INTEGRATION_MATRIX",
    "CompatibilityRecord",
    "get_compatibility_matrix",
    "process_otlp_http_bytes",
    "compute_raw_payload_hash",
    "IngestionError",
    "UnsupportedMediaTypeError",
    "PayloadTooLargeError"
]
