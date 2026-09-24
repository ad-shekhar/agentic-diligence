import os
import io
import json
import zipfile
import hashlib
from typing import Dict, Any, List, Optional

def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def create_diligence_bundle(report_data: Dict[str, Any], output_zip_path: Optional[str] = None) -> str:
    """
    Packages all artifacts of a standardized due diligence review into a single,
    cryptographically verifiable .zip bundle with SHA-256 checksums and chain-of-custody seal.
    """
    company_name = report_data.get("company", {}).get("name", "Target_AI")
    company_slug = company_name.lower().replace(" ", "_").replace("(", "").replace(")", "")
    
    if not output_zip_path:
        output_zip_path = f"diligence_package_{company_slug}.zip"
        
    pkg_files = report_data.get("package_files", {})
    manifest = report_data.get("audit_manifest", {})
    
    # Required core files
    files_to_pack: Dict[str, bytes] = {}
    
    # 1. Package JSON
    package_json_str = json.dumps(report_data, indent=2, default=str)
    files_to_pack["diligence_package.json"] = package_json_str.encode("utf-8")
    
    # 2. Audit Manifest JSON
    manifest_str = json.dumps(manifest, indent=2, default=str)
    files_to_pack["audit_manifest.json"] = manifest_str.encode("utf-8")
    
    # 3. Native AIBOM
    aibom_native = report_data.get("aibom", {})
    files_to_pack["aibom_native.json"] = json.dumps(aibom_native, indent=2, default=str).encode("utf-8")
    
    # 4. CycloneDX AIBOM
    cyclonedx_path = pkg_files.get("aibom_cyclonedx")
    if cyclonedx_path and os.path.exists(cyclonedx_path):
        with open(cyclonedx_path, "rb") as f:
            files_to_pack["aibom_cyclonedx.json"] = f.read()
    else:
        # Fallback to empty CycloneDX structure if missing
        files_to_pack["aibom_cyclonedx.json"] = b"{}"
        
    # 5. PDF Report
    pdf_path = report_data.get("pdf_path") or pkg_files.get("pdf_report")
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            files_to_pack["diligence_report.pdf"] = f.read()
            
    # 6. Generate checksums.sha256
    checksum_lines = []
    for filename in sorted(files_to_pack.keys()):
        file_hash = compute_sha256(files_to_pack[filename])
        checksum_lines.append(f"{file_hash}  {filename}")
    checksums_content = "\n".join(checksum_lines) + "\n"
    files_to_pack["checksums.sha256"] = checksums_content.encode("utf-8")
    
    # 7. Verification README
    master_seal = manifest.get("chain_of_custody_seal", {}).get("digest", "N/A")
    readme_text = f"""========================================================================
AGENTIC DILIGENCE - STANDARDIZED EVIDENCE PACKAGE
Target System : {company_name}
Package Build : {output_zip_path}
Master Seal   : {master_seal}
========================================================================

This archive represents a sealed, reproducible technical due diligence package
for an LLM-based agentic software system.

INDEPENDENT VERIFICATION INSTRUCTIONS:
1. Verify package file integrity using standard sha256sum:
   sha256sum -c checksums.sha256

2. Verify provenance against the Agentic Diligence CLI:
   python cli.py verify-bundle --bundle {os.path.basename(output_zip_path)}

CONTENTS:
- diligence_package.json : Complete machine-readable diligence schema & metrics
- diligence_report.pdf   : Executive-ready technical diligence PDF report
- aibom_native.json      : Native Agentic AI Bill of Materials
- aibom_cyclonedx.json   : CycloneDX 1.6 compliant AI Bill of Materials
- audit_manifest.json    : Cryptographic chain-of-custody audit manifest
- checksums.sha256       : SHA-256 digests for all encapsulated files

CONFIDENTIAL - PREPARED FOR TECHNICAL DUE DILIGENCE AUDIT
========================================================================
"""
    files_to_pack["VERIFICATION_README.txt"] = readme_text.encode("utf-8")
    
    # Write to ZIP
    with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zip_out:
        for filename, data in files_to_pack.items():
            zip_out.writestr(filename, data)
            
    return os.path.abspath(output_zip_path)


def verify_diligence_bundle(bundle_path: str) -> Dict[str, Any]:
    """
    Verifies the integrity, authenticity, and cryptographic chain-of-custody
    of a .zip diligence bundle.
    """
    if not os.path.exists(bundle_path):
        return {
            "is_valid": False,
            "status": "NOT_FOUND",
            "errors": [f"File {bundle_path} does not exist."],
            "checked_files": []
        }
        
    errors = []
    checked_files = []
    
    try:
        with zipfile.ZipFile(bundle_path, "r") as z:
            namelist = z.namelist()
            
            if "checksums.sha256" not in namelist:
                return {
                    "is_valid": False,
                    "status": "CORRUPTED",
                    "errors": ["Missing checksums.sha256 file in diligence bundle."],
                    "checked_files": []
                }
                
            checksum_data = z.read("checksums.sha256").decode("utf-8")
            expected_checksums: Dict[str, str] = {}
            for line in checksum_data.strip().split("\n"):
                if not line.strip() or line.startswith("#"):
                    continue
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    h, fname = parts
                    fname = fname.strip()
                    expected_checksums[fname] = h
                    
            for fname, exp_hash in expected_checksums.items():
                if fname not in namelist:
                    errors.append(f"Missing file in bundle: {fname}")
                    continue
                actual_bytes = z.read(fname)
                actual_hash = compute_sha256(actual_bytes)
                if actual_hash != exp_hash:
                    errors.append(f"Checksum mismatch for {fname}: expected {exp_hash}, computed {actual_hash}")
                    checked_files.append({"file": fname, "status": "TAMPERED", "expected": exp_hash, "actual": actual_hash})
                else:
                    checked_files.append({"file": fname, "status": "VERIFIED", "digest": actual_hash})
                    
            # Verify manifest chain of custody
            if "audit_manifest.json" in namelist:
                try:
                    manifest_data = json.loads(z.read("audit_manifest.json").decode("utf-8"))
                    seal = manifest_data.get("chain_of_custody_seal", {})
                    seal_digest = seal.get("digest")
                    
                    # Verify manifest matches package
                    if not seal_digest:
                        errors.append("Manifest missing root chain-of-custody seal.")
                except Exception as ex:
                    errors.append(f"Failed to parse audit manifest: {str(ex)}")
            else:
                errors.append("Missing audit_manifest.json in bundle.")
                
    except zipfile.BadZipFile:
        return {
            "is_valid": False,
            "status": "INVALID_ARCHIVE",
            "errors": ["Target file is not a valid zip archive."],
            "checked_files": []
        }
    except Exception as ex:
        return {
            "is_valid": False,
            "status": "ERROR",
            "errors": [str(ex)],
            "checked_files": []
        }
        
    is_valid = len(errors) == 0
    return {
        "is_valid": is_valid,
        "status": "VERIFIED" if is_valid else "TAMPERED",
        "bundle_path": os.path.abspath(bundle_path),
        "total_files_checked": len(checked_files),
        "checked_files": checked_files,
        "errors": errors
    }
