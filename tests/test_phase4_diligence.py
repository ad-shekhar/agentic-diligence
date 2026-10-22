"""
Phase 4 Regression and Acceptance Tests: Claim Verification Matrix,
Canonical Reports, Manifest Integrity, CycloneDX Validation, API & CLI.
"""

import os
import json
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal, init_db
from app.db.models import Company, Trace, Span, Claim, PayloadProvenance
from app.epistemic.tags import EpistemicTag, TrustLevel, VerificationVerdict, ConfidenceBounds, EpistemicValue
from app.epistemic.claims import ClaimDimension, ComparisonOperator, ClaimSchema
from app.evidence.claim_matrix import (
    ClaimVerificationMatrix, ClaimVerificationMatrixEntry,
    EvidenceReference, evaluate_single_claim, generate_claim_verification_matrix
)
from app.reporting.manifest import (
    ArtifactEntry, ArtifactType, SerializationMethod, VerificationStatus,
    canonicalize_json, compute_canonical_sha256, compute_sha256_bytes,
    build_evidence_manifest, verify_bundle_integrity
)
from app.reporting.canonical_report import (
    build_canonical_diligence_report, render_markdown_diligence_report,
    DiligenceVerdict, EpistemicConfidence
)
from app.reporting.service import (
    assemble_company_evidence, load_company_claims,
    assemble_canonical_diligence_report_package, compile_diligence_bundle_on_disk
)
from app.aibom.schema import NativeAIBOM, ModelAsset, ToolAsset
from app.aibom.generator import export_cyclonedx_aibom, validate_cyclonedx_schema
from cli import cli


client = TestClient(app)


# ==============================================================================
# 1. CLAIM VERIFICATION MATRIX TESTS
# ==============================================================================

def test_claim_verification_supported():
    """Claim with observed lower bound >= target is VERIFIED."""
    claim = ClaimSchema(
        claim_id="CLM-101",
        dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="90% autonomy",
        target_operator=ComparisonOperator.GREATER_EQUAL,
        target_value=90.0,
        unit="%"
    )
    evidence = EpistemicValue(
        value=95.0,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=92.0, point_estimate=95.0, upper=98.0),
        sample_size=30,
        unknown_fraction=0.05
    )
    entry = evaluate_single_claim(claim, evidence)
    assert entry.verification_verdict == VerificationVerdict.VERIFIED
    assert "meets or exceeds target" in entry.verdict_reason


def test_claim_verification_partially_verified():
    """Claim within tolerance margin is PARTIALLY_VERIFIED."""
    claim = ClaimSchema(
        claim_id="CLM-102",
        dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="90% autonomy",
        target_operator=ComparisonOperator.GREATER_EQUAL,
        target_value=90.0,
        unit="%",
        tolerance_pct=5.0
    )
    # Lower bound at 87% (within 5% tolerance of 90)
    evidence = EpistemicValue(
        value=89.0,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=87.0, point_estimate=89.0, upper=92.0),
        sample_size=25,
        unknown_fraction=0.05
    )
    entry = evaluate_single_claim(claim, evidence)
    assert entry.verification_verdict == VerificationVerdict.PARTIALLY_VERIFIED
    assert "within allowable tolerance margin" in entry.verdict_reason


def test_claim_verification_contradicted():
    """Claim significantly violated by observed bounds is CONTRADICTED."""
    claim = ClaimSchema(
        claim_id="CLM-103",
        dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="90% autonomy",
        target_operator=ComparisonOperator.GREATER_EQUAL,
        target_value=90.0,
        unit="%",
        tolerance_pct=5.0
    )
    # Lower bound at 65% (far below 90)
    evidence = EpistemicValue(
        value=70.0,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=65.0, point_estimate=70.0, upper=75.0),
        sample_size=40,
        unknown_fraction=0.10
    )
    entry = evaluate_single_claim(claim, evidence)
    assert entry.verification_verdict == VerificationVerdict.CONTRADICTED
    assert "contradicts claim" in entry.verdict_reason


def test_claim_verification_insufficient_sample_size():
    """Evidence with N < 15 produces INSUFFICIENT_EVIDENCE."""
    claim = ClaimSchema(
        claim_id="CLM-104",
        dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="90% autonomy",
        target_operator=ComparisonOperator.GREATER_EQUAL,
        target_value=90.0,
        unit="%"
    )
    evidence = EpistemicValue(
        value=95.0,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=90.0, point_estimate=95.0, upper=100.0),
        sample_size=10,  # Below minimum 15
        unknown_fraction=0.0
    )
    entry = evaluate_single_claim(claim, evidence, min_sample_size=15)
    assert entry.verification_verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE
    assert "insufficient (minimum requirement: 15)" in entry.verdict_reason


def test_claim_verification_empty_evidence_set():
    """Empty or None evidence set produces INSUFFICIENT_EVIDENCE with explicit absence notice."""
    claim = ClaimSchema(
        claim_id="CLM-105",
        dimension=ClaimDimension.PROVIDER_SPREAD,
        stated_claim_text="Multi-cloud HHI <= 3500",
        target_operator=ComparisonOperator.LESS_EQUAL,
        target_value=3500.0,
        unit="HHI"
    )
    entry = evaluate_single_claim(claim, evidence=None)
    assert entry.verification_verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE
    assert entry.observed_epistemic_value.sample_size == 0
    assert "Absence of runtime evidence" in entry.verdict_reason


def test_claim_verification_excessive_unknown_dark_zones():
    """Evidence with unknown fraction > 35% produces INSUFFICIENT_EVIDENCE."""
    claim = ClaimSchema(
        claim_id="CLM-106",
        dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="80% autonomy",
        target_operator=ComparisonOperator.GREATER_EQUAL,
        target_value=80.0,
        unit="%"
    )
    evidence = EpistemicValue(
        value=85.0,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=50.0, point_estimate=85.0, upper=95.0),
        sample_size=50,
        unknown_fraction=0.45  # 45% dark zone
    )
    entry = evaluate_single_claim(claim, evidence)
    assert entry.verification_verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE
    assert "Uninstrumented intervals represent 45.0%" in entry.verdict_reason


def test_claim_verification_trust_ladder_enforcement():
    """T0 evidence cannot verify a claim requiring T1+ runtime telemetry."""
    claim = ClaimSchema(
        claim_id="CLM-107",
        dimension=ClaimDimension.AUTONOMY,
        stated_claim_text="90% autonomy",
        target_operator=ComparisonOperator.GREATER_EQUAL,
        target_value=90.0,
        unit="%",
        evidence_trust_minimum=TrustLevel.T1
    )
    evidence = EpistemicValue(
        value=95.0,
        tag=EpistemicTag.INFERRED,
        trust_level=TrustLevel.T0,  # Self-reported
        bounds=ConfidenceBounds(lower=90.0, point_estimate=95.0, upper=100.0),
        sample_size=50,
        unknown_fraction=0.0
    )
    entry = evaluate_single_claim(claim, evidence)
    assert entry.verification_verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE
    assert "Self-reports cannot verify runtime claims" in entry.verdict_reason


def test_claim_verification_boundary_values():
    """Boundary test: exactly at target value."""
    claim = ClaimSchema(
        claim_id="CLM-108",
        dimension=ClaimDimension.UNIT_COST,
        stated_claim_text="Cost per task <= $0.10",
        target_operator=ComparisonOperator.LESS_EQUAL,
        target_value=0.1000,
        unit="USD",
        tolerance_pct=0.0
    )
    # Exactly at 0.1000
    evidence = EpistemicValue(
        value=0.1000,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=0.08, point_estimate=0.10, upper=0.1000),
        sample_size=30,
        unknown_fraction=0.0
    )
    entry = evaluate_single_claim(claim, evidence)
    assert entry.verification_verdict == VerificationVerdict.VERIFIED


# ==============================================================================
# 2. ARTIFACT MANIFEST & BUNDLE INTEGRITY TESTS
# ==============================================================================

def test_canonical_json_determinism():
    """Canonical JSON serializer produces bit-for-bit identical bytes regardless of key insertion order."""
    dict1 = {"z": 1, "a": [3, 2, 1], "m": {"b": 2, "a": 1}}
    dict2 = {"a": [3, 2, 1], "m": {"a": 1, "b": 2}, "z": 1}

    bytes1 = canonicalize_json(dict1, pretty=False)
    bytes2 = canonicalize_json(dict2, pretty=False)

    assert bytes1 == bytes2
    assert compute_canonical_sha256(dict1) == compute_canonical_sha256(dict2)


def test_bundle_integrity_valid(tmp_path):
    """A completely intact bundle passes verification with status VALID."""
    bundle_dir = str(tmp_path / "test_bundle_valid")
    os.makedirs(bundle_dir, exist_ok=True)

    file1 = os.path.join(bundle_dir, "data.json")
    content1 = {"key": "value", "count": 42}
    with open(file1, "wb") as f:
        f.write(canonicalize_json(content1, pretty=True))

    file2 = os.path.join(bundle_dir, "readme.txt")
    with open(file2, "w", encoding="utf-8") as f:
        f.write("Evidence bundle documentation")

    artifacts = [
        ArtifactEntry(
            path="data.json",
            artifact_type="canonical_metrics",
            sha256=compute_canonical_sha256(content1, pretty=True),
            byte_size=os.path.getsize(file1),
            serialization_method=SerializationMethod.CANONICAL_JSON_PRETTY.value
        ),
        ArtifactEntry(
            path="readme.txt",
            artifact_type="diligence_report_markdown",
            sha256=compute_sha256_bytes(b"Evidence bundle documentation"),
            byte_size=os.path.getsize(file2),
            serialization_method=SerializationMethod.UTF8_TEXT.value
        )
    ]

    manifest = build_evidence_manifest("comp-test", artifacts)
    with open(os.path.join(bundle_dir, "manifest.json"), "wb") as f:
        f.write(canonicalize_json(manifest, pretty=True))

    res = verify_bundle_integrity(bundle_dir)
    assert res.is_valid is True
    assert res.status == VerificationStatus.VALID
    assert res.files_verified == 2
    assert len(res.missing_files) == 0
    assert len(res.altered_files) == 0


def test_bundle_integrity_tamper_detection(tmp_path):
    """Altering a single byte in an artifact causes INTEGRITY_VIOLATION."""
    bundle_dir = str(tmp_path / "test_bundle_tamper")
    os.makedirs(bundle_dir, exist_ok=True)

    file1 = os.path.join(bundle_dir, "data.json")
    content1 = {"key": "original_value"}
    with open(file1, "wb") as f:
        f.write(canonicalize_json(content1, pretty=True))

    artifacts = [
        ArtifactEntry(
            path="data.json",
            artifact_type="canonical_metrics",
            sha256=compute_canonical_sha256(content1, pretty=True),
            byte_size=os.path.getsize(file1),
            serialization_method=SerializationMethod.CANONICAL_JSON_PRETTY.value
        )
    ]
    manifest = build_evidence_manifest("comp-test", artifacts)
    with open(os.path.join(bundle_dir, "manifest.json"), "wb") as f:
        f.write(canonicalize_json(manifest, pretty=True))

    # Tamper with file1
    with open(file1, "wb") as f:
        f.write(canonicalize_json({"key": "tampered_value"}, pretty=True))

    res = verify_bundle_integrity(bundle_dir)
    assert res.is_valid is False
    assert res.status == VerificationStatus.INTEGRITY_VIOLATION
    assert len(res.altered_files) == 1
    assert res.altered_files[0]["path"] == "data.json"


def test_bundle_integrity_missing_file_detection(tmp_path):
    """Deleting a declared artifact causes CORRUPTED_BUNDLE."""
    bundle_dir = str(tmp_path / "test_bundle_missing")
    os.makedirs(bundle_dir, exist_ok=True)

    artifacts = [
        ArtifactEntry(
            path="nonexistent_artifact.json",
            artifact_type="raw_telemetry",
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            byte_size=100
        )
    ]
    manifest = build_evidence_manifest("comp-test", artifacts)
    with open(os.path.join(bundle_dir, "manifest.json"), "wb") as f:
        f.write(canonicalize_json(manifest, pretty=True))

    res = verify_bundle_integrity(bundle_dir)
    assert res.is_valid is False
    assert res.status == VerificationStatus.CORRUPTED_BUNDLE
    assert "nonexistent_artifact.json" in res.missing_files


def test_bundle_integrity_untracked_files_detection(tmp_path):
    """An extra undeclared file in bundle causes UNTRACKED_ARTIFACT_DETECTED."""
    bundle_dir = str(tmp_path / "test_bundle_extra")
    os.makedirs(bundle_dir, exist_ok=True)

    file1 = os.path.join(bundle_dir, "declared.txt")
    with open(file1, "w", encoding="utf-8") as f:
        f.write("declared content")

    artifacts = [
        ArtifactEntry(
            path="declared.txt",
            artifact_type="diligence_report_markdown",
            sha256=compute_sha256_bytes(b"declared content"),
            byte_size=os.path.getsize(file1),
            serialization_method=SerializationMethod.UTF8_TEXT.value
        )
    ]
    manifest = build_evidence_manifest("comp-test", artifacts)
    with open(os.path.join(bundle_dir, "manifest.json"), "wb") as f:
        f.write(canonicalize_json(manifest, pretty=True))

    # Add untracked extra file
    extra_file = os.path.join(bundle_dir, "rogue_extra.bin")
    with open(extra_file, "wb") as f:
        f.write(b"untracked payload")

    res = verify_bundle_integrity(bundle_dir)
    assert res.status == VerificationStatus.UNTRACKED_ARTIFACT_DETECTED
    assert "rogue_extra.bin" in res.untracked_files


# ==============================================================================
# 3. CANONICAL DILIGENCE REPORTS TESTS
# ==============================================================================

def test_canonical_report_schema_and_markdown():
    """Canonical report adheres to schema and Markdown contains synthetic warning if flagged."""
    claims = [
        ClaimSchema(
            claim_id="CLM-001",
            dimension=ClaimDimension.AUTONOMY,
            stated_claim_text="90% autonomy",
            target_operator=ComparisonOperator.GREATER_EQUAL,
            target_value=90.0,
            unit="%"
        )
    ]
    ev = EpistemicValue(
        value=95.0,
        tag=EpistemicTag.CALCULATED,
        trust_level=TrustLevel.T1,
        bounds=ConfidenceBounds(lower=91.0, point_estimate=95.0, upper=99.0),
        sample_size=30,
        unknown_fraction=0.05
    )
    matrix = generate_claim_verification_matrix("comp-test", claims, {"autonomy": ev})

    scope = {
        "total_traces_analyzed": 5,
        "total_spans_analyzed": 50,
        "total_tasks_segmented": 20,
        "evidence_trust_summary": {"T1": 50},
        "unobserved_intervals_count": 0
    }
    signals = {
        "autonomy": {
            "value": 95.0,
            "metric_name": "autonomy_rate",
            "tag": "[CALCULATED]",
            "trust_level": "T1",
            "bounds": {"lower": 91.0, "point": 95.0, "upper": 99.0},
            "unknown_fraction": 0.05,
            "notes": "Verified"
        }
    }

    report = build_canonical_diligence_report(
        company_id="comp-test",
        company_name="Test Robotics",
        scope=scope,
        signals=signals,
        claim_matrix=matrix,
        trace_payload_digests=["hash-123"],
        is_synthetic=True
    )

    assert report["schema_version"] == "1.0.0"
    assert report["is_synthetic"] is True
    assert report["executive_summary"]["overall_verdict"] == DiligenceVerdict.PASS_WITH_CONDITIONS.value

    # Render Markdown
    md = render_markdown_diligence_report(report)
    assert "SYNTHETIC DATASET — BENCHMARK DEMONSTRATION" in md
    assert "NOT READY FOR SHARED DEPLOYMENT" in md
    assert "| `CLM-001` |" in md
    assert "[CALCULATED]" in md


# ==============================================================================
# 4. CYCLONEDX AI-BOM SCHEMA VALIDATION TESTS
# ==============================================================================

def test_cyclonedx_16_schema_validation():
    """Generated CycloneDX 1.6 AI-BOM strictly validates against official OWASP JSON schema."""
    native = NativeAIBOM(
        bom_id="BOM-CDX-16",
        generated_at="2026-10-22T12:00:00Z",
        company_id="comp-alpha",
        company_name="Alpha Intelligent Systems",
        observation_window="Last 30 Days",
        total_traces_analyzed=20,
        total_spans_analyzed=100,
        models=[
            ModelAsset(
                model_name="claude-3-5-sonnet",
                provider_name="anthropic",
                hosting_type="cloud_api",
                total_prompt_tokens=50000,
                total_completion_tokens=10000,
                measured_cost_usd=0.30,
                call_count=20,
                parameter_tier="large"
            )
        ],
        tools=[
            ToolAsset(
                tool_name="web_search",
                tool_type="retrieval",
                call_count=15,
                failure_count=0,
                failure_rate_pct=0.0,
                avg_latency_ms=120.5
            )
        ],
        vector_stores=[],
        external_apis=[],
        frameworks=[],
        human_checkpoints=[],
        total_model_spend_usd=0.30,
        unique_model_count=1,
        unique_tool_count=1,
        has_self_hosted_models=False,
        has_human_checkpoints=False
    )

    cdx = export_cyclonedx_aibom(native, spec_version="1.6")
    is_valid, errors = validate_cyclonedx_schema(cdx, spec_version="1.6")
    assert is_valid is True, f"CycloneDX 1.6 validation failed: {errors}"


def test_cyclonedx_15_schema_validation():
    """Generated CycloneDX 1.5 AI-BOM strictly validates against official OWASP 1.5 JSON schema."""
    native = NativeAIBOM(
        bom_id="BOM-CDX-15",
        generated_at="2026-10-22T12:00:00Z",
        company_id="comp-beta",
        company_name="Beta Reasoning Ltd",
        observation_window="Last 30 Days",
        total_traces_analyzed=10,
        total_spans_analyzed=40,
        models=[
            ModelAsset(
                model_name="gpt-4o-mini",
                provider_name="openai",
                hosting_type="cloud_api",
                total_prompt_tokens=20000,
                total_completion_tokens=4000,
                measured_cost_usd=0.05,
                call_count=10,
                parameter_tier="small"
            )
        ],
        tools=[],
        vector_stores=[],
        external_apis=[],
        frameworks=[],
        human_checkpoints=[],
        total_model_spend_usd=0.05,
        unique_model_count=1,
        unique_tool_count=0,
        has_self_hosted_models=False,
        has_human_checkpoints=False
    )

    cdx = export_cyclonedx_aibom(native, spec_version="1.5")
    is_valid, errors = validate_cyclonedx_schema(cdx, spec_version="1.5")
    assert is_valid is True, f"CycloneDX 1.5 validation failed: {errors}"


def test_cyclonedx_negative_validation():
    """Malformed or invalid BOM fails schema validation with explicit error message."""
    invalid_bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        # Missing required 'serialNumber' and 'version'
        "components": [{"name": "test"}]
    }
    is_valid, errors = validate_cyclonedx_schema(invalid_bom, spec_version="1.6")
    assert is_valid is False
    assert len(errors) > 0


# ==============================================================================
# 5. API ROUTES INTEGRATION TESTS
# ==============================================================================

def test_api_claim_matrix_endpoint():
    """GET /companies/{id}/claim-matrix returns valid JSON structure."""
    response = client.get("/api/v1/companies/scenario_a/claim-matrix")
    if response.status_code == 200:
        data = response.json()
        assert "matrix_id" in data
        assert "entries" in data
        assert "summary" in data


def test_api_diligence_report_endpoints():
    """GET /companies/{id}/diligence-report returns JSON and Markdown."""
    res_json = client.get("/api/v1/companies/scenario_a/diligence-report?format=json")
    if res_json.status_code == 200:
        d = res_json.json()
        assert d["schema_version"] == "1.0.0"
        assert "executive_summary" in d
        assert "claim_matrix" in d

    res_md = client.get("/api/v1/companies/scenario_a/diligence-report?format=markdown")
    if res_md.status_code == 200:
        assert "# Technical Due Diligence Report" in res_md.text


def test_api_cyclonedx_headers():
    """GET /companies/{id}/aibom/cyclonedx returns validation status headers."""
    res = client.get("/api/v1/companies/scenario_a/aibom/cyclonedx?spec_version=1.6")
    if res.status_code == 200:
        assert res.headers.get("X-CycloneDX-SpecVersion") == "1.6"
        assert res.headers.get("X-CycloneDX-Valid") in ("true", "false")


def test_api_bundle_verify_endpoint(tmp_path):
    """POST /bundles/verify executes bundle verification correctly."""
    bundle_dir = str(tmp_path / "api_test_bundle")
    os.makedirs(bundle_dir, exist_ok=True)
    fpath = os.path.join(bundle_dir, "test.txt")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("hello")

    artifacts = [
        ArtifactEntry(
            path="test.txt",
            artifact_type="diligence_report_markdown",
            sha256=compute_sha256_bytes(b"hello"),
            byte_size=5,
            serialization_method=SerializationMethod.UTF8_TEXT.value
        )
    ]
    manifest = build_evidence_manifest("api-comp", artifacts)
    with open(os.path.join(bundle_dir, "manifest.json"), "wb") as f:
        f.write(canonicalize_json(manifest, pretty=True))

    resp = client.post("/api/v1/bundles/verify", json={"bundle_dir": bundle_dir})
    assert resp.status_code == 200
    res = resp.json()
    assert res["status"] == "VALID"
    assert res["is_valid"] is True


# ==============================================================================
# 6. CLI INTEGRATION TESTS
# ==============================================================================

def test_cli_claim_matrix_command():
    """CLI claim-matrix command executes cleanly."""
    runner = CliRunner()
    result = runner.invoke(cli, ["claim-matrix", "--company", "scenario_a"])
    assert result.exit_code == 0
    assert "CLAIM VERIFICATION MATRIX" in result.output


def test_cli_report_markdown_command():
    """CLI report command outputs markdown."""
    runner = CliRunner()
    result = runner.invoke(cli, ["report", "--company", "scenario_a", "--format", "markdown"])
    assert result.exit_code == 0
    assert "Technical Due Diligence Report" in result.output


def test_cli_bundle_verify_command(tmp_path):
    """CLI bundle verify command checks a bundle directory."""
    bundle_dir = str(tmp_path / "cli_test_bundle")
    os.makedirs(bundle_dir, exist_ok=True)
    fpath = os.path.join(bundle_dir, "test.txt")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("content")

    artifacts = [
        ArtifactEntry(
            path="test.txt",
            artifact_type="diligence_report_markdown",
            sha256=compute_sha256_bytes(b"content"),
            byte_size=7,
            serialization_method=SerializationMethod.UTF8_TEXT.value
        )
    ]
    manifest = build_evidence_manifest("cli-comp", artifacts)
    with open(os.path.join(bundle_dir, "manifest.json"), "wb") as f:
        f.write(canonicalize_json(manifest, pretty=True))

    runner = CliRunner()
    result = runner.invoke(cli, ["bundle", "verify", "--dir", bundle_dir])
    assert result.exit_code == 0
    assert "BUNDLE INTEGRITY VERIFICATION RESULT: [VALID]" in result.output


def test_cli_aibom_command():
    """CLI aibom command exports CycloneDX 1.6 and validates against schema."""
    runner = CliRunner()
    result = runner.invoke(cli, ["aibom", "--company", "scenario_a", "--spec-version", "1.6", "--validate"])
    assert result.exit_code == 0
    assert "Schema Validation: PASSED" in result.output
