"""
Phase 4.5 Adversarial Audit Test Suite.
Reproduces and verifies findings ADV-001 through ADV-007.
"""

import os
import json
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from app.main import app
from app.epistemic.tags import EpistemicTag, TrustLevel, VerificationVerdict, ConfidenceBounds, EpistemicValue
from app.epistemic.claims import ClaimDimension, ComparisonOperator, ClaimSchema
from app.evidence.claim_matrix import evaluate_single_claim
from app.reporting.manifest import (
    ArtifactEntry, SerializationMethod, VerificationStatus,
    canonicalize_json, compute_canonical_sha256, build_evidence_manifest,
    verify_bundle_integrity
)
from app.db.session import SessionLocal, init_db
from app.aibom.generator import generate_native_aibom, export_cyclonedx_aibom, validate_cyclonedx_schema
from cli import cli


client = TestClient(app)


# ==============================================================================
# ADV-001: Missing/Unknown Evidence (value=None) Must Not Convert to 0.0 & Success
# ==============================================================================

def test_adv001_missing_evidence_value_none_must_not_produce_verified():
    """
    ADV-001: When evidence.value is None and bounds is None, evaluate_single_claim
    must return INSUFFICIENT_EVIDENCE, NOT convert to 0.0 and claim VERIFIED.
    """
    claim = ClaimSchema(
        claim_id="CLM-ADV-001",
        dimension=ClaimDimension.UNIT_COST,
        stated_claim_text="Cost per task <= $0.10",
        target_operator=ComparisonOperator.LESS_EQUAL,
        target_value=0.10,
        unit="USD"
    )
    # Evidence has valid sample size and low unknown fraction, but value is None (missing/unknown metric)
    evidence = EpistemicValue(
        value=None,
        tag=EpistemicTag.UNKNOWN,
        trust_level=TrustLevel.T1,
        bounds=None,
        sample_size=20,
        unknown_fraction=0.10,
        notes="Cost could not be computed for unpriced model."
    )
    res = evaluate_single_claim(claim, evidence)
    assert res.verification_verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE, (
        f"Expected INSUFFICIENT_EVIDENCE but got {res.verification_verdict}. Missing evidence was converted to zero!"
    )
    assert "no numeric value" in res.verdict_reason.lower() or "missing" in res.verdict_reason.lower() or "unknown" in res.verdict_reason.lower()


# ==============================================================================
# ADV-002: Path Traversal in Bundle Verification
# ==============================================================================

def test_adv002_manifest_path_traversal_escaping_bundle_root_rejected(tmp_path):
    """
    ADV-002: Manifest containing path traversal (e.g. '../secret.txt') or absolute path
    must be rejected and must NOT read files outside bundle_dir.
    """
    bundle_dir = tmp_path / "bundle_safe"
    os.makedirs(bundle_dir, exist_ok=True)

    # Secret file outside bundle root
    secret_file = tmp_path / "host_secret.txt"
    secret_file.write_text("SUPER_SECRET_KEY_12345")

    # Craft malicious manifest pointing outside bundle_dir
    manifest_data = {
        "manifest_version": "1.0.0",
        "bundle_id": "malicious-bundle-001",
        "company_id": "attacker-target",
        "created_at_utc": "2026-10-23T00:00:00Z",
        "generator_version": "agd-0.4.0",
        "artifacts": [
            {
                "path": "../host_secret.txt",
                "artifact_type": "raw_telemetry",
                "sha256": "any_hash",
                "byte_size": 100,
                "serialization_method": "raw_bytes",
                "epistemic_trust_level": "T1"
            }
        ],
        "summary": {"total_files": 1, "total_bytes": 100, "min_trust_level": "T1"}
    }
    with open(bundle_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)

    res = verify_bundle_integrity(str(bundle_dir))
    assert res.is_valid is False
    assert res.status in (VerificationStatus.CORRUPTED_BUNDLE, VerificationStatus.INTEGRITY_VIOLATION)
    assert "traversal" in (res.error_message or "").lower() or "escapes" in (res.error_message or "").lower()


def test_adv002_manifest_absolute_path_rejected(tmp_path):
    """
    ADV-002: Manifest containing absolute path must be rejected.
    """
    bundle_dir = tmp_path / "bundle_abs"
    os.makedirs(bundle_dir, exist_ok=True)

    abs_path = os.path.abspath(str(tmp_path / "some_file.txt"))
    manifest_data = {
        "manifest_version": "1.0.0",
        "bundle_id": "abs-path-bundle",
        "company_id": "test-comp",
        "created_at_utc": "2026-10-23T00:00:00Z",
        "generator_version": "agd-0.4.0",
        "artifacts": [
            {
                "path": abs_path,
                "artifact_type": "raw_telemetry",
                "sha256": "hash",
                "byte_size": 10,
                "serialization_method": "raw_bytes",
                "epistemic_trust_level": "T1"
            }
        ],
        "summary": {"total_files": 1, "total_bytes": 10, "min_trust_level": "T1"}
    }
    with open(bundle_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)

    res = verify_bundle_integrity(str(bundle_dir))
    assert res.is_valid is False
    assert "absolute" in (res.error_message or "").lower() or "traversal" in (res.error_message or "").lower()


# ==============================================================================
# ADV-003: Fabricated Pinecone & Hardcoded Orchestrator Inferences
# ==============================================================================

def test_adv003_no_fabricated_pinecone_without_vector_telemetry():
    """
    ADV-003: If tools or spans mention 'rag' or 'vector', generate_native_aibom
    must NOT invent 'pinecone' or 'text-embedding-3-small' without telemetry evidence.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.session import Base
    from app.db.models import Tenant, Company, Trace, Span

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        tenant = Tenant(name="RAG Test Tenant")
        db.add(tenant)
        db.flush()

        comp = Company(id="comp-rag-test", tenant_id=tenant.id, name="RAG Test Co")
        db.add(comp)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        trace = Trace(
            id="tr-rag-01",
            company_id="comp-rag-test",
            name="rag_trace",
            start_time=now,
            end_time=now,
            duration_ms=10.0
        )
        db.add(trace)
        span = Span(
            id="sp-rag-01",
            trace_id="tr-rag-01",
            name="rag_query_tool",
            span_kind="tool",
            tool_name="rag_search",
            attributes_json={"query": "test"}, # No vector_db system specified!
            start_time=now,
            end_time=now,
            duration_ms=10.0
        )
        db.add(span)
        db.commit()

        native_bom = generate_native_aibom(db, "comp-rag-test")
        pinecone_entries = [vs for vs in native_bom.vector_stores if vs.system_name == "pinecone"]
        assert len(pinecone_entries) == 0, "Fabricated 'pinecone' vector store was injected without telemetry evidence!"
    finally:
        db.close()


# ==============================================================================
# ADV-004: GREATER_EQUAL Relative Tolerance Evaluation
# ==============================================================================

def test_adv004_greater_equal_non_percentage_tolerance():
    """
    ADV-004: For non-percentage metrics (e.g. ratio, dollars), abs(diff) <= tol
    must NOT allow raw 5.0 unit difference when target is 0.50.
    """
    claim = ClaimSchema(
        claim_id="CLM-ADV-004",
        dimension=ClaimDimension.UNIT_COST,
        stated_claim_text="Efficiency >= 0.50",
        target_operator=ComparisonOperator.GREATER_EQUAL,
        target_value=0.50,
        unit="ratio",
        tolerance_pct=5.0
    )
    # 0.0 observed is a 100% shortfall, not within 5% tolerance!
    evidence = EpistemicValue(
        value=0.0,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=0.0, point_estimate=0.0, upper=0.0),
        sample_size=25,
        unknown_fraction=0.0
    )
    res = evaluate_single_claim(claim, evidence)
    assert res.verification_verdict == VerificationVerdict.CONTRADICTED, (
        f"0.0 observed against 0.50 target was marked {res.verification_verdict}! Should be CONTRADICTED."
    )


# ==============================================================================
# ADV-005: Duplicate Artifact Paths in Manifest Rejected
# ==============================================================================

def test_adv005_duplicate_artifact_paths_rejected(tmp_path):
    """
    ADV-005: Manifest containing duplicate declared paths must be rejected as CORRUPTED_BUNDLE.
    """
    bundle_dir = tmp_path / "bundle_dup"
    os.makedirs(bundle_dir, exist_ok=True)
    fpath = bundle_dir / "data.txt"
    fpath.write_text("sample content")

    manifest_data = {
        "manifest_version": "1.0.0",
        "bundle_id": "dup-paths-bundle",
        "company_id": "test-comp",
        "created_at_utc": "2026-10-23T00:00:00Z",
        "generator_version": "agd-0.4.0",
        "artifacts": [
            {
                "path": "data.txt",
                "artifact_type": "raw_telemetry",
                "sha256": "hash1",
                "byte_size": 14,
                "serialization_method": "utf8_text",
                "epistemic_trust_level": "T1"
            },
            {
                "path": "data.txt",
                "artifact_type": "raw_telemetry",
                "sha256": "hash2",
                "byte_size": 14,
                "serialization_method": "utf8_text",
                "epistemic_trust_level": "T1"
            }
        ],
        "summary": {"total_files": 2, "total_bytes": 28, "min_trust_level": "T1"}
    }
    with open(bundle_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)

    res = verify_bundle_integrity(str(bundle_dir))
    assert res.is_valid is False
    assert res.status == VerificationStatus.CORRUPTED_BUNDLE
    assert "duplicate" in (res.error_message or "").lower()


# ==============================================================================
# ADV-006: CycloneDX Validation Failure Status Code & CLI Exit Code
# ==============================================================================

def test_adv006_cyclonedx_validation_failure_status_in_api(monkeypatch):
    """
    ADV-006: When CycloneDX schema validation fails, the API must return HTTP 422,
    not HTTP 200 OK with success appearance.
    """
    from app.aibom import generator
    # Monkeypatch validate_cyclonedx_schema to simulate a schema validation failure
    monkeypatch.setattr(
        generator,
        "validate_cyclonedx_schema",
        lambda bom, spec_version="1.6": (False, ["Simulated schema error: missing required component property"])
    )

    res = client.get("/api/v1/companies/scenario_a/aibom/cyclonedx?spec_version=1.6")
    assert res.status_code == 422, f"Expected 422 Unprocessable Entity on schema failure, got {res.status_code}"
    assert "validation failed" in res.text.lower()


# ==============================================================================
# ADV-007: Bundle Directory Traversal Restriction in API
# ==============================================================================

def test_adv007_api_verify_bundle_path_traversal_rejected():
    """
    ADV-007: POST /api/v1/bundles/verify with path traversal or absolute non-bundle paths
    must be rejected with HTTP 400.
    """
    res = client.post("/api/v1/bundles/verify", json={"bundle_dir": "../../Windows/System32"})
    assert res.status_code == 400
    assert "invalid" in res.text.lower() or "traversal" in res.text.lower() or "not found" in res.text.lower()
