"""
Artifact Manifest & Chain of Custody Specification Engine (Phase 4).

Implements docs/phase-4/manifest-spec.md for cryptographic provenance,
canonical JSON serialization, byte-level hash verification, and bundle tamper detection.
"""

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple, Set


class SerializationMethod(str, Enum):
    RAW_BYTES = "raw_bytes"
    CANONICAL_JSON_COMPACT = "canonical_json_compact"
    CANONICAL_JSON_PRETTY = "canonical_json_pretty"
    UTF8_TEXT = "utf8_text"


class ArtifactType(str, Enum):
    RAW_TELEMETRY = "raw_telemetry"
    NORMALIZED_SPANS = "normalized_spans"
    TASK_SEGMENTATION = "task_segmentation"
    CANONICAL_METRICS = "canonical_metrics"
    CLAIM_VERIFICATION_MATRIX = "claim_verification_matrix"
    CYCLONEDX_AIBOM = "cyclonedx_aibom"
    DILIGENCE_REPORT_JSON = "diligence_report_json"
    DILIGENCE_REPORT_MARKDOWN = "diligence_report_markdown"


class VerificationStatus(str, Enum):
    VALID = "VALID"
    CORRUPTED_BUNDLE = "CORRUPTED_BUNDLE"
    INTEGRITY_VIOLATION = "INTEGRITY_VIOLATION"
    UNTRACKED_ARTIFACT_DETECTED = "UNTRACKED_ARTIFACT_DETECTED"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"


@dataclass
class ArtifactEntry:
    path: str
    artifact_type: str
    sha256: str
    byte_size: int
    serialization_method: str = SerializationMethod.CANONICAL_JSON_COMPACT.value
    epistemic_trust_level: str = "T1"
    origin_reference: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "path": self.path.replace("\\", "/"),
            "artifact_type": self.artifact_type,
            "sha256": self.sha256,
            "byte_size": self.byte_size,
            "serialization_method": self.serialization_method,
            "epistemic_trust_level": self.epistemic_trust_level,
        }
        if self.origin_reference:
            d["origin_reference"] = self.origin_reference
        return d


@dataclass
class BundleVerificationResult:
    status: VerificationStatus
    is_valid: bool
    manifest_version: str
    total_files_declared: int
    files_verified: int
    missing_files: List[str] = field(default_factory=list)
    altered_files: List[Dict[str, str]] = field(default_factory=list)
    untracked_files: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "is_valid": self.is_valid,
            "manifest_version": self.manifest_version,
            "total_files_declared": self.total_files_declared,
            "files_verified": self.files_verified,
            "missing_files": list(self.missing_files),
            "altered_files": list(self.altered_files),
            "untracked_files": list(self.untracked_files),
            "error_message": self.error_message,
            "warnings": list(self.warnings)
        }


def compute_sha256_bytes(data: bytes) -> str:
    """Computes exact SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_sha256_file(filepath: str) -> str:
    """Computes exact SHA-256 hex digest of a file on disk."""
    if not os.path.exists(filepath):
        return "file_not_found"
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def canonicalize_json(data: Any, pretty: bool = False) -> bytes:
    """
    Deterministic canonical JSON serializer conforming to docs/phase-4/manifest-spec.md:
    - Encoding: UTF-8
    - Key Sorting: Strictly alphabetical (sort_keys=True)
    - Separators: Compact (',', ':') or Pretty (',', ': ')
    - Line endings: Unix LF (\n)
    """
    indent = 2 if pretty else None
    separators = (',', ': ') if pretty else (',', ':')
    json_str = json.dumps(
        data,
        sort_keys=True,
        indent=indent,
        separators=separators,
        ensure_ascii=False,
        default=str
    )
    if pretty and not json_str.endswith('\n'):
        json_str += '\n'
    return json_str.encode('utf-8')


def compute_canonical_sha256(data: Any, pretty: bool = False) -> str:
    """Computes SHA-256 hex digest of canonically serialized JSON data."""
    return hashlib.sha256(canonicalize_json(data, pretty=pretty)).hexdigest()


def build_evidence_manifest(
    company_id: str,
    artifacts: List[ArtifactEntry],
    bundle_id: Optional[str] = None,
    generator_version: str = "agd-0.4.0"
) -> Dict[str, Any]:
    """
    Builds a versioned artifact manifest conforming to docs/phase-4/manifest-spec.md (v1.0).
    Note: The manifest does NOT include its own hash to prevent circular hashing.
    """
    b_id = bundle_id or str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    total_bytes = sum(a.byte_size for a in artifacts)
    
    trust_ranks = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}
    min_trust = "T3"
    if artifacts:
        min_trust = min(
            (a.epistemic_trust_level for a in artifacts),
            key=lambda t: trust_ranks.get(t, 1)
        )
    else:
        min_trust = "T0"

    return {
        "manifest_version": "1.0.0",
        "bundle_id": b_id,
        "company_id": company_id,
        "created_at_utc": timestamp,
        "generator_version": generator_version,
        "artifacts": [a.to_dict() for a in artifacts],
        "summary": {
            "total_files": len(artifacts),
            "total_bytes": total_bytes,
            "min_trust_level": min_trust
        }
    }


def verify_bundle_integrity(
    bundle_dir: str,
    manifest_filename: str = "manifest.json"
) -> BundleVerificationResult:
    """
    Verifies the cryptographic integrity and completeness of an evidence bundle:
    1. Checks manifest file existence and valid schema version.
    2. Verifies presence of each declared artifact.
    3. Hashes each artifact (raw or canonical JSON) and verifies against declared SHA-256.
    4. Scans for untracked artifacts within bundle subdirectories.
    """
    manifest_path = os.path.join(bundle_dir, manifest_filename)
    if not os.path.exists(manifest_path):
        return BundleVerificationResult(
            status=VerificationStatus.CORRUPTED_BUNDLE,
            is_valid=False,
            manifest_version="unknown",
            total_files_declared=0,
            files_verified=0,
            error_message=f"Manifest file '{manifest_filename}' not found in bundle directory."
        )

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
    except Exception as e:
        return BundleVerificationResult(
            status=VerificationStatus.CORRUPTED_BUNDLE,
            is_valid=False,
            manifest_version="unknown",
            total_files_declared=0,
            files_verified=0,
            error_message=f"Manifest JSON malformed: {str(e)}"
        )

    version = manifest_data.get("manifest_version", "")
    if version != "1.0.0":
        return BundleVerificationResult(
            status=VerificationStatus.UNSUPPORTED_SCHEMA,
            is_valid=False,
            manifest_version=version,
            total_files_declared=0,
            files_verified=0,
            error_message=f"Unsupported manifest version '{version}'. Expected '1.0.0'."
        )

    artifacts_list = manifest_data.get("artifacts", [])
    total_declared = len(artifacts_list)
    missing_files: List[str] = []
    altered_files: List[Dict[str, str]] = []
    declared_paths: Set[str] = set()
    files_verified = 0

    for art in artifacts_list:
        rel_path = art.get("path", "").replace("/", os.sep)
        declared_paths.add(os.path.normpath(rel_path))
        full_path = os.path.join(bundle_dir, rel_path)
        expected_sha = art.get("sha256", "")
        method = art.get("serialization_method", SerializationMethod.CANONICAL_JSON_COMPACT.value)

        if not os.path.exists(full_path):
            missing_files.append(art.get("path", ""))
            continue

        # Compute hash according to declared serialization method
        actual_sha = ""
        try:
            with open(full_path, "rb") as f:
                content_bytes = f.read()

            if method == SerializationMethod.RAW_BYTES.value or method == SerializationMethod.UTF8_TEXT.value:
                actual_sha = hashlib.sha256(content_bytes).hexdigest()
            elif method in (SerializationMethod.CANONICAL_JSON_COMPACT.value, SerializationMethod.CANONICAL_JSON_PRETTY.value):
                # Try parsing and re-canonicalizing; if fail, fallback to raw bytes
                try:
                    obj = json.loads(content_bytes.decode("utf-8"))
                    actual_sha = hashlib.sha256(canonicalize_json(
                        obj,
                        pretty=(method == SerializationMethod.CANONICAL_JSON_PRETTY.value)
                    )).hexdigest()
                except Exception:
                    actual_sha = hashlib.sha256(content_bytes).hexdigest()
            else:
                actual_sha = hashlib.sha256(content_bytes).hexdigest()
        except Exception as e:
            altered_files.append({
                "path": art.get("path", ""),
                "expected_sha256": expected_sha,
                "actual_sha256": "error_reading_file",
                "reason": str(e)
            })
            continue

        if actual_sha.lower() != expected_sha.lower():
            altered_files.append({
                "path": art.get("path", ""),
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha
            })
        else:
            files_verified += 1

    # Check for untracked files in the bundle directory
    untracked_files: List[str] = []
    ignored_basenames = {manifest_filename, ".DS_Store", "Thumbs.db"}
    for root, dirs, files in os.walk(bundle_dir):
        # Ignore common hidden directories
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for fname in files:
            if fname in ignored_basenames or fname.endswith(".pyc") or fname.endswith(".tmp"):
                continue
            full_file = os.path.join(root, fname)
            rel_file = os.path.normpath(os.path.relpath(full_file, bundle_dir))
            if rel_file not in declared_paths:
                untracked_files.append(rel_file.replace(os.sep, "/"))

    # Determine status
    warnings: List[str] = []
    if missing_files:
        return BundleVerificationResult(
            status=VerificationStatus.CORRUPTED_BUNDLE,
            is_valid=False,
            manifest_version=version,
            total_files_declared=total_declared,
            files_verified=files_verified,
            missing_files=missing_files,
            altered_files=altered_files,
            untracked_files=untracked_files,
            error_message=f"{len(missing_files)} declared artifact(s) are missing from the bundle."
        )

    if altered_files:
        return BundleVerificationResult(
            status=VerificationStatus.INTEGRITY_VIOLATION,
            is_valid=False,
            manifest_version=version,
            total_files_declared=total_declared,
            files_verified=files_verified,
            missing_files=missing_files,
            altered_files=altered_files,
            untracked_files=untracked_files,
            error_message=f"{len(altered_files)} artifact(s) exhibited cryptographic hash mismatches."
        )

    if untracked_files:
        warnings.append(f"{len(untracked_files)} untracked file(s) found in bundle directory.")
        return BundleVerificationResult(
            status=VerificationStatus.UNTRACKED_ARTIFACT_DETECTED,
            is_valid=True,  # All declared artifacts are intact, but bundle has untracked files
            manifest_version=version,
            total_files_declared=total_declared,
            files_verified=files_verified,
            missing_files=[],
            altered_files=[],
            untracked_files=untracked_files,
            warnings=warnings
        )

    return BundleVerificationResult(
        status=VerificationStatus.VALID,
        is_valid=True,
        manifest_version=version,
        total_files_declared=total_declared,
        files_verified=files_verified,
        missing_files=[],
        altered_files=[],
        untracked_files=[],
        warnings=[]
    )


# --- Legacy Phase 1-3 Support ---
def build_chain_of_custody_manifest(
    company_id: str,
    company_name: str,
    trace_hashes: List[str],
    evidence_records: List[Dict[str, Any]],
    report_json_str: str,
    pdf_path: str,
    aibom_native_str: str,
    aibom_cyclonedx_str: str
) -> Dict[str, Any]:
    """
    Constructs an immutable cryptographic chain-of-custody manifest capturing hashes
    and versions across the entire processing chain for full audit reproducibility.
    Retained for backward compatibility with Phase 1–3 callers and tests.
    """
    manifest_id = f"MAN-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # 1. Input Telemetry Aggregate Hash
    combined_trace_hashes = "".join(sorted(trace_hashes if trace_hashes else ["empty_trace_set"]))
    input_telemetry_sha256 = hashlib.sha256(combined_trace_hashes.encode("utf-8")).hexdigest()
    
    # 2. Evidence Graph Hash
    evidence_str = json.dumps(evidence_records, sort_keys=True, default=str)
    evidence_graph_sha256 = hashlib.sha256(evidence_str.encode("utf-8")).hexdigest()
    
    # 3. Artifact Hashes
    report_json_sha256 = hashlib.sha256(report_json_str.encode("utf-8")).hexdigest()
    pdf_sha256 = compute_sha256_file(pdf_path) if pdf_path else "uncompiled"
    aibom_native_sha256 = hashlib.sha256(aibom_native_str.encode("utf-8")).hexdigest()
    aibom_cyclonedx_sha256 = hashlib.sha256(aibom_cyclonedx_str.encode("utf-8")).hexdigest()
    
    # 4. Master Verification Seal (Chain Seal)
    chain_seal_material = f"{input_telemetry_sha256}:{evidence_graph_sha256}:{report_json_sha256}:{pdf_sha256}:{aibom_native_sha256}"
    master_verification_seal = hashlib.sha256(chain_seal_material.encode("utf-8")).hexdigest()
    
    return {
        "manifest_version": "1.0.0",
        "manifest_id": manifest_id,
        "generated_at": timestamp,
        "company": {
            "id": company_id,
            "name": company_name
        },
        "pipeline_stages": {
            "1_telemetry_input": {
                "trace_count": len(trace_hashes),
                "aggregate_telemetry_sha256": input_telemetry_sha256,
                "provenance_type": "OpenTelemetry GenAI Spans"
            },
            "2_normalization": {
                "engine": "OTel-GenAI-Normalizer",
                "version": "v0.1.0-norm",
                "standard": "OpenTelemetry GenAI Semantic Conventions v1.26+"
            },
            "3_deterministic_analysis": {
                "engine": "Agentic-Diligence-Analytics",
                "version": "v0.1.0-engine",
                "components": [
                    "autonomy_hir_calculator",
                    "unit_economics_calculator",
                    "evaluation_trust_tax_engine",
                    "provider_hhi_engine",
                    "cascade_failure_analyzer",
                    "potential_spof_evaluator"
                ]
            },
            "4_pricing_model": {
                "table_version": "v2026_09",
                "status": "frozen_reference",
                "currency": "USD"
            },
            "5_evidence_graph": {
                "record_count": len(evidence_records),
                "evidence_graph_sha256": evidence_graph_sha256
            }
        },
        "artifacts": {
            "diligence_package_json": {
                "filename": "diligence_package.json",
                "sha256": report_json_sha256,
                "mime_type": "application/json"
            },
            "diligence_report_pdf": {
                "filename": os.path.basename(pdf_path) if pdf_path else "diligence_report.pdf",
                "sha256": pdf_sha256,
                "mime_type": "application/pdf"
            },
            "aibom_native": {
                "filename": "aibom_native.json",
                "sha256": aibom_native_sha256,
                "mime_type": "application/json"
            },
            "aibom_cyclonedx": {
                "filename": "aibom_cyclonedx.json",
                "sha256": aibom_cyclonedx_sha256,
                "mime_type": "application/vnd.cyclonedx+json"
            }
        },
        "chain_of_custody_seal": {
            "algorithm": "SHA-256",
            "digest": master_verification_seal,
            "verification_status": "cryptographically_anchored"
        }
    }
