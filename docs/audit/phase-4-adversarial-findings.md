# Phase 4.5 Adversarial Audit Findings Register

**Repository:** `agentic-diligence` (`agd`)  
**Branch:** `feat/phase-04-claim-verification-reporting`  
**Audit Head Commit:** `077866f`  
**Audit Date:** 2026-10-23  
**Auditor Role:** Independent Principal Security & Methodology Auditor  
**Pre-Audit Test Baseline:** 191 passing tests (115 baseline + 51 Phase 1–3 audit tests + 25 Phase 4 tests)  
**Post-Remediation Test Results:** 199 passing tests (0 failures, 3 non-blocking deprecation warnings)  

---

## Finding Severity Legend

| Severity | Definition |
|---|---|
| **P0** | False verification from core logic, data corruption, trust bypass, path escape allowing remote host traversal |
| **P1** | Metric math defect, missing evidence converted to success, fabricated/unsupported dependencies in AI-BOM |
| **P2** | Input validation defect, HTTP status code ambiguity, duplicate declarations in integrity manifest |
| **P3** | Non-blocking telemetry warning, documentation or metadata discrepancy |

---

## Confirmed Findings & Remediations

### ADV-001 — Missing/Unknown Evidence (`value=None`) Silently Converted to 0.0 and Positive Verdict (P0)

- **Affected Files:** `app/evidence/claim_matrix.py`, `app/epistemic/claims.py`
- **Functions:** `evaluate_single_claim()`
- **Epistemic Invariant Violated:** "Absence of evidence is not evidence of absence. Never convert missing evidence into zero or success."
- **Description:**
  When evidence was evaluated with `evidence.value is None` and `evidence.bounds is None` (e.g. an uninstrumented metric or an unobserved metric dimension), `evaluate_single_claim` executed:
  ```python
  val = evidence.value if evidence.value is not None else 0.0
  ```
  If a claim evaluated a `LESS_EQUAL` condition (e.g. Cost per Task <= $0.10, or P95 Latency <= 500ms), `val` was set to `0.0`. Since `0.0 <= 0.10` evaluates to `True`, the claim verifier emitted `VerificationVerdict.VERIFIED`.
- **Impact:**
  Agentic Diligence would certify that a customer's agent met stringent cost, latency, or error ceilings when zero telemetry or metric data existed for that dimension.
- **Minimal Reproduction:**
  ```python
  claim = ClaimSchema(
      claim_id="CLM-01",
      dimension=ClaimDimension.UNIT_COST,
      stated_claim_text="Cost per task <= $0.10",
      target_operator=ComparisonOperator.LESS_EQUAL,
      target_value=0.10,
      unit="USD"
  )
  evidence = EpistemicValue(
      value=None,
      tag=EpistemicTag.UNKNOWN,
      trust_level=TrustLevel.T0,
      bounds=None,
      sample_size=0,
      unknown_fraction=1.0
  )
  res = evaluate_single_claim(claim, evidence)
  assert res.verification_verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE
  ```
- **Remediation:**
  Refactored `evaluate_single_claim` in both `app/evidence/claim_matrix.py` and `app/epistemic/claims.py`:
  1. If `evidence.value is None` and `evidence.bounds is None`, or if `evidence.tag == EpistemicTag.UNKNOWN`, immediately emit `VerificationVerdict.INSUFFICIENT_EVIDENCE` with an explicit reason string.
  2. For point estimate evaluation, require `evidence.value is not None`; never substitute `0.0`.
- **Regression Test:** `tests/test_phase4_adversarial_audit.py::test_adv001_missing_evidence_value_none_must_not_produce_verified`
- **Resolution:** FIXED

---

### ADV-002 — Bundle Manifest Path Traversal and Absolute Path Escaping (P0)

- **Affected File:** `app/reporting/manifest.py`
- **Functions:** `verify_bundle_integrity()`
- **Security Invariant Violated:** Evidence bundles must be hermetically self-contained. Integrity verification must never read, hash, or inspect files outside the designated bundle directory.
- **Description:**
  `verify_bundle_integrity()` joined `bundle_dir` with `artifact.path` via `os.path.join(bundle_dir, artifact.path)` without verifying whether the resulting path escaped `bundle_dir`. Furthermore, on POSIX and Windows systems, `os.path.join("/bundle", "/etc/passwd")` discards the first argument when the second argument is an absolute path. Consequently, an adversarial manifest could declare paths such as `../../etc/passwd` or `C:\Windows\win.ini`.
- **Impact:**
  A caller supplying a malicious `manifest.json` could force the diligence verifier to compute checksums over arbitrary local system files, verify their existence or contents, or induce directory traversal during bundle auditing.
- **Minimal Reproduction:**
  ```python
  manifest_data = {
      "manifest_version": "1.0.0",
      "bundle_id": "traversal-bundle",
      "company_id": "test",
      "artifacts": [{
          "path": "../../../sensitive.txt",
          "artifact_type": "raw_telemetry",
          "sha256": "any",
          "byte_size": 10,
          "serialization_method": "raw_bytes",
          "epistemic_trust_level": "T1"
      }]
  }
  # verify_bundle_integrity must reject this bundle as CORRUPTED_BUNDLE / INTEGRITY_VIOLATION
  ```
- **Remediation:**
  Enhanced `verify_bundle_integrity` in `app/reporting/manifest.py`:
  1. Inspect `artifact.path` and reject any path where `os.path.isabs(artifact.path)` is true.
  2. Reject any path containing `..` path segments (`".." in norm_path.split(os.sep)`).
  3. Resolve the canonical absolute path via `os.path.realpath(full_path)` and verify via `os.path.commonpath([bundle_root, resolved_path]) == bundle_root` to prevent symlink and alias escapes.
  4. Emit `VerificationStatus.CORRUPTED_BUNDLE` with `is_valid=False` if any path fails validation.
- **Regression Tests:**
  - `tests/test_phase4_adversarial_audit.py::test_adv002_manifest_path_traversal_escaping_bundle_root_rejected`
  - `tests/test_phase4_adversarial_audit.py::test_adv002_manifest_absolute_path_rejected`
- **Resolution:** FIXED

---

### ADV-003 — Heuristic Fabrication of Unobserved Vector Stores and Orchestrators in Native AI-BOM (P1)

- **Affected File:** `app/aibom/generator.py`
- **Functions:** `generate_native_aibom()`
- **Epistemic Invariant Violated:** "Never label a result as observed when it is inferred. Never invent dependencies without empirical evidence."
- **Description:**
  In `generate_native_aibom()`, if any tool span contained `"rag"` or `"vector"` anywhere in its name, the code heuristically fabricated a Pinecone vector database entry and an OpenAI embedding model:
  ```python
  vector_stores.append(VectorStoreEntry(
      system_name="pinecone",
      index_name="knowledge-base-v1",
      embedding_model="text-embedding-3-small"
  ))
  ```
  Furthermore, if no agent frameworks were detected, it injected a hardcoded orchestrator framework:
  ```python
  frameworks.append(FrameworkEntry(
      name="Custom Distributed Orchestrator",
      version="1.0.0",
      inferred=True
  ))
  ```
- **Impact:**
  The AI-BOM falsely certified specific proprietary software components (`pinecone`, `text-embedding-3-small`, `Custom Distributed Orchestrator`) that did not exist in the customer's runtime environment, corrupting software supply chain diligence.
- **Minimal Reproduction:**
  A trace containing a tool named `rag_search` with no vector database telemetry was ingested. `generate_native_aibom` reported `system_name="pinecone"` under `vector_stores`.
- **Remediation:**
  1. Removed hardcoded heuristic injection of Pinecone and OpenAI embedding models.
  2. Vector stores are now extracted strictly from telemetry attributes (e.g. `vector_db.system`, `db.system`) present on spans.
  3. Only real frameworks detected from agent metadata or span attributes are populated in `frameworks`.
- **Regression Test:** `tests/test_phase4_adversarial_audit.py::test_adv003_no_fabricated_pinecone_without_vector_telemetry`
- **Resolution:** FIXED

---

### ADV-004 — GREATER_EQUAL Tolerance Uses Raw Absolute Difference for Non-Percentage Scales (P1)

- **Affected Files:** `app/evidence/claim_matrix.py`, `app/epistemic/claims.py`
- **Functions:** `evaluate_single_claim()`
- **Epistemic Invariant Violated:** Numerical tolerances must scale proportionally to the target value and unit dimension.
- **Description:**
  For `GREATER_EQUAL` claims with `tolerance_pct`, the code checked:
  ```python
  diff = claim.target_value - val
  if diff > 0 and abs(diff) <= claim.tolerance_pct:
      return ClaimEvaluationResult(verification_verdict=VerificationVerdict.PARTIALLY_VERIFIED, ...)
  ```
  If a metric had unit `"ratio"` (or `"USD"`) with `target_value = 0.50` and `tolerance_pct = 5.0`, an observed value of `0.0` produced `diff = 0.50`. Because `0.50 <= 5.0` is `True`, an agent with complete 100% failure (`0.0` vs `0.50`) was granted `PARTIALLY_VERIFIED`.
- **Impact:**
  Agents failing severely on small-scale metrics (e.g., benchmark ratios 0.0–1.0, dollar unit costs) were marked partially verified due to subtracting a percentage quantity from a non-percentage base.
- **Minimal Reproduction:**
  ```python
  claim = ClaimSchema(
      claim_id="CLM-GE-01",
      dimension=ClaimDimension.UNIT_COST,
      stated_claim_text="Task Success Ratio >= 0.50",
      target_operator=ComparisonOperator.GREATER_EQUAL,
      target_value=0.50,
      unit="ratio",
      tolerance_pct=5.0
  )
  evidence = EpistemicValue(value=0.0, ...)
  res = evaluate_single_claim(claim, evidence)
  # Must be CONTRADICTED, not PARTIALLY_VERIFIED
  ```
- **Remediation:**
  Updated tolerance evaluation to compute relative percentage shortfall for non-percentage metrics:
  ```python
  if claim.unit == "%":
      within_tol = abs(diff) <= claim.tolerance_pct
  else:
      rel_shortfall_pct = (abs(diff) / abs(claim.target_value)) * 100.0 if claim.target_value != 0 else float("inf")
      within_tol = rel_shortfall_pct <= claim.tolerance_pct
  ```
- **Regression Test:** `tests/test_phase4_adversarial_audit.py::test_adv004_greater_equal_non_percentage_tolerance`
- **Resolution:** FIXED

---

### ADV-005 — Duplicate Artifact Paths in Manifest Increment Verified Counter (P2)

- **Affected File:** `app/reporting/manifest.py`
- **Functions:** `verify_bundle_integrity()`
- **Epistemic Invariant Violated:** Artifact declarations in an integrity manifest must be unique and non-overlapping.
- **Description:**
  If a manifest listed the same file path multiple times (e.g., declaring `raw_telemetry.json` three times), `verify_bundle_integrity` checked each entry against the disk file and incremented `verified_files += 1`. This allowed an incomplete bundle (missing other required files) to report `verified_files == summary.total_files`.
- **Impact:**
  A bundle missing declared files could appear completely verified if duplicate valid entries artificially inflated `verified_files`.
- **Minimal Reproduction:**
  A manifest with 2 entries declaring the identical path `data.txt` with identical or distinct hashes.
- **Remediation:**
  Added duplicate path detection in `verify_bundle_integrity`:
  ```python
  seen_paths = set()
  for art in manifest.artifacts:
      if art.path in seen_paths:
          return BundleVerificationResult(
              is_valid=False,
              status=VerificationStatus.CORRUPTED_BUNDLE,
              error_message=f"Duplicate artifact path declared in manifest: '{art.path}'"
          )
      seen_paths.add(art.path)
  ```
- **Regression Test:** `tests/test_phase4_adversarial_audit.py::test_adv005_duplicate_artifact_paths_rejected`
- **Resolution:** FIXED

---

### ADV-006 — CycloneDX Schema Validation Failure Returned HTTP 200 OK (P2)

- **Affected File:** `app/api/routes.py`
- **Endpoints:** `GET /api/v1/companies/{company_id}/aibom/cyclonedx`
- **Security & Contract Invariant Violated:** Schema validation failures must return an HTTP 4xx error code and must not present invalid data as valid.
- **Description:**
  When `validate_cyclonedx_schema(bom_dict, spec_version)` returned `(False, errors)`, the endpoint logged a warning, attached an `X-BOM-Validation: FAILED` header, and proceeded to return HTTP 200 OK with the invalid BOM payload.
- **Impact:**
  Automated client pipelines receiving HTTP 200 would ingest unvalidated or non-compliant CycloneDX BOMs into enterprise software supply chain systems.
- **Minimal Reproduction:**
  Simulated schema validation error in `validate_cyclonedx_schema`. Endpoint returned status code 200.
- **Remediation:**
  Updated `get_cyclonedx_aibom` in `app/api/routes.py` to raise `HTTPException(status_code=422, detail={"error": "CycloneDX validation failed", "validation_errors": errors})` when schema validation fails.
- **Regression Test:** `tests/test_phase4_adversarial_audit.py::test_adv006_cyclonedx_validation_failure_status_in_api`
- **Resolution:** FIXED

---

### ADV-007 — Arbitrary Local Directory Traversal via `POST /api/v1/bundles/verify` (P1)

- **Affected File:** `app/api/routes.py`
- **Endpoints:** `POST /api/v1/bundles/verify`
- **Security Invariant Violated:** Untrusted client input must not direct server file I/O to arbitrary directories outside the bundles repository.
- **Description:**
  `POST /api/v1/bundles/verify` accepted a JSON payload `{"bundle_dir": str}` and passed it directly to `verify_bundle_integrity(req.bundle_dir)` without path validation. A client could pass arbitrary directory paths or path traversal sequences (`../../Windows/System32`).
- **Impact:**
  API callers could inspect, probe, or verify arbitrary server directories, facilitating directory enumeration and local file existence probing.
- **Minimal Reproduction:**
  `POST /api/v1/bundles/verify` with body `{"bundle_dir": "../../Windows/System32"}` returned HTTP 200 with directory inspection results.
- **Remediation:**
  In `app/api/routes.py`:
  1. Sanitized and normalized `bundle_dir`.
  2. Disallowed `..` traversal sequences.
  3. Ensured that `bundle_dir` exists and is a directory.
  4. Confirmed that `bundle_dir` is located within the application working directory or bundle repository roots.
  5. Raised `HTTPException(status_code=400, detail="Invalid bundle directory: path traversal or unauthorized directory")` on violations.
- **Regression Test:** `tests/test_phase4_adversarial_audit.py::test_adv007_api_verify_bundle_path_traversal_rejected`
- **Resolution:** FIXED

---

## Retained Deployment Blockers & Architectural Limitations

### L-001 — Tenant Authentication & Authorization Remaining Unimplemented (P0 Security)

- **Affected System:** Global API surface (`app/api/routes.py`)
- **Status:** **DEPLOYMENT BLOCKER**
- **Description:**
  All API endpoints accept arbitrary `company_id` without verifying that the requesting user or client token has authorization for that tenant. Local operation and single-tenant testing do not establish tenant isolation.
- **Condition for Deployment:** The platform must not be deployed to multi-tenant or internet-accessible environments until cryptographic JWT authentication and row-level tenant authorization are implemented and verified.
