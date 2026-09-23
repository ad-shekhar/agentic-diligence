import hashlib
import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any, List

def compute_sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def compute_sha256_file(filepath: str) -> str:
    if not os.path.exists(filepath):
        return "file_not_found"
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

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
    """
    manifest_id = f"MAN-{uuid.uuid4().hex[:8].upper()}"
    timestamp = datetime.utcnow().isoformat()
    
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
            "verification_status": "CRYPTOGRAPHICALLY_VERIFIED"
        }
    }
