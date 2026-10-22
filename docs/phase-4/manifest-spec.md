# Artifact Manifest Specification (v1.0)

**Version:** 1.0.0  
**Status:** Approved Post-Audit Specification  
**Date:** 2026-10-22  
**Dependency:** Phase 1–3 Audit Complete  

---

## 1. Overview & Epistemic Purpose

The Artifact Manifest provides a tamper-evident audit trail linking raw OpenTelemetry runtime evidence payloads to downstream canonical metrics, claim verifications, AI-BOM exports, and human-facing diligence reports.

> **Principle:** A hash manifest proves integrity and consistency against a recorded state, NOT absolute authenticity or completeness of unobserved execution. Cryptographic digital signatures are required if non-repudiation of the author is claimed.

---

## 2. Canonical Serialization Rules

To ensure reproducible cryptographic digests across platforms (Windows, Linux, macOS) and environments:

1. **Raw Files (Exact Byte Hashing):**
   - Ingested OTLP JSON / Protobuf payloads.
   - Benchmark fixtures (`tests/fixtures/real_traces/*.json`).
   - Standard binary or static evidence artifacts.
   - **Method:** `hashlib.sha256(raw_bytes).hexdigest()`.

2. **Structured Artifacts (Canonical JSON Hashing):**
   - Canonical metrics output, Claim Verification Matrix, AI-BOM representations.
   - **Method:**
     - Encoding: UTF-8.
     - Key Sorting: Strictly alphabetical (`sort_keys=True`).
     - Whitespace: No trailing whitespace, standard separators (`separators=(',', ':')`).
     - Line Endings: Standard Unix LF (`\n`) if pretty-printed, though compact serialization is preferred for hashing.
     - Numbers: Floats formatted without redundant trailing zeroes; scientific notation normalized.

3. **Manifest Non-Circularity:**
   - The manifest file itself (`manifest.json`) MUST NOT attempt to contain its own SHA-256 hash.
   - An external verification signature file (`manifest.sig`) or a parent packaging container (e.g. tar/zip bundle hash) may be used to verify the manifest itself.

---

## 3. Manifest JSON Schema (v1.0)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ArtifactManifest",
  "type": "object",
  "required": [
    "manifest_version",
    "bundle_id",
    "company_id",
    "created_at_utc",
    "generator_version",
    "artifacts",
    "summary"
  ],
  "properties": {
    "manifest_version": {
      "type": "string",
      "const": "1.0.0"
    },
    "bundle_id": {
      "type": "string",
      "description": "Unique UUIDv4 identifying this diligence artifact collection"
    },
    "company_id": {
      "type": "string"
    },
    "created_at_utc": {
      "type": "string",
      "format": "date-time"
    },
    "generator_version": {
      "type": "string",
      "description": "Agentic Diligence release identifier, e.g. agd-0.4.0"
    },
    "artifacts": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "path",
          "artifact_type",
          "sha256",
          "byte_size",
          "serialization_method",
          "epistemic_trust_level"
        ],
        "properties": {
          "path": {
            "type": "string",
            "description": "Relative POSIX-style path from bundle root (e.g., 'evidence/raw/batch_01.json')"
          },
          "artifact_type": {
            "type": "string",
            "enum": [
              "raw_telemetry",
              "normalized_spans",
              "task_segmentation",
              "canonical_metrics",
              "claim_verification_matrix",
              "cyclonedx_aibom",
              "diligence_report_json",
              "diligence_report_markdown"
            ]
          },
          "sha256": {
            "type": "string",
            "pattern": "^[a-f0-9]{64}$"
          },
          "byte_size": {
            "type": "integer",
            "minimum": 0
          },
          "serialization_method": {
            "type": "string",
            "enum": ["raw_bytes", "canonical_json_compact", "canonical_json_pretty", "utf8_text"]
          },
          "epistemic_trust_level": {
            "type": "string",
            "enum": ["T0", "T1", "T2", "T3"]
          },
          "origin_reference": {
            "type": "string",
            "description": "Parent artifact hash or ingestion batch ID for provenance linking"
          }
        }
      }
    },
    "summary": {
      "type": "object",
      "required": ["total_files", "total_bytes", "min_trust_level"],
      "properties": {
        "total_files": {"type": "integer"},
        "total_bytes": {"type": "integer"},
        "min_trust_level": {"type": "string", "enum": ["T0", "T1", "T2", "T3"]}
      }
    }
  }
}
```

---

## 4. Verification Semantics

When validating an artifact bundle against `manifest.json`:

1. **Missing Files:**
   - If any file listed in `artifacts` is missing from the bundle: Verification fails immediately with status `CORRUPTED_BUNDLE` and lists all missing file paths.

2. **Modified Files:**
   - Each present file is read, serialized/hashed according to its specified `serialization_method`, and compared against the recorded `sha256`.
   - Any mismatch causes immediate failure with status `INTEGRITY_VIOLATION` reporting both expected and actual hashes.

3. **Extra / Untracked Files:**
   - Any file present in the directory structure not recorded in `artifacts`:
     - If in an excluded path (e.g. `.git/`, `__pycache__/`, `.DS_Store`): Ignored.
     - If in an evidence or output path: Flagged with warning `UNTRACKED_ARTIFACT_DETECTED` and recorded in verification notes.

4. **Digital Signatures (Phase 4.2 Extension):**
   - If an optional `manifest.sig` is present, it must be verified with the corresponding auditor public key. If absent, the bundle is marked `VERIFIED_UNAUTHENTICATED` (checksum verified, author identity unasserted).
