import pytest
import os
import json
from app.reporting.manifest import build_chain_of_custody_manifest, compute_sha256_file

def test_chain_of_custody_manifest(tmp_path):
    # Create sample dummy PDF
    dummy_pdf = tmp_path / "sample.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 dummy content")
    
    trace_hashes = [
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "ca978112ca1bbdcafac231b39a23dc4da786081496542749e755567a29e248b6"
    ]
    evidence_records = [
        {"evidence_code": "EVD-001", "observed_fact": "Test fact", "status": "VERIFIED"}
    ]
    report_json_str = json.dumps({"test": "value"})
    aibom_native_str = json.dumps({"models": []})
    aibom_cyclonedx_str = json.dumps({"bomFormat": "CycloneDX"})
    
    manifest = build_chain_of_custody_manifest(
        company_id="comp-123",
        company_name="Test Corp",
        trace_hashes=trace_hashes,
        evidence_records=evidence_records,
        report_json_str=report_json_str,
        pdf_path=str(dummy_pdf),
        aibom_native_str=aibom_native_str,
        aibom_cyclonedx_str=aibom_cyclonedx_str
    )
    
    assert manifest["manifest_id"].startswith("MAN-")
    assert manifest["company"]["id"] == "comp-123"
    assert manifest["pipeline_stages"]["1_telemetry_input"]["trace_count"] == 2
    assert "chain_of_custody_seal" in manifest
    assert len(manifest["chain_of_custody_seal"]["digest"]) == 64
    assert manifest["artifacts"]["diligence_report_pdf"]["sha256"] == compute_sha256_file(str(dummy_pdf))
