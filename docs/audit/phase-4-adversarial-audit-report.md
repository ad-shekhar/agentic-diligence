# Phase 4.5 Independent Adversarial Technical Audit Report

**Repository:** `agentic-diligence` (`agd`)  
**Branch:** `feat/phase-04-claim-verification-reporting`  
**Head Commit:** `077866f`  
**Audit Date:** 2026-10-23  
**Auditor:** Independent Principal Security & Methodology Auditor  
**Scope:** Phase 4 Claim Verification Matrix, Evidence Bundles, Canonical Reports, CycloneDX AI-BOM, and HTTP/CLI Attack Surface  
**Final Status:** **PASS WITH CONDITIONS**  

---

## 1. Executive Summary & Test Baselines

An independent adversarial correctness and security audit was conducted on Phase 4 of `agentic-diligence`. The audit evaluated whether the implementation upholds the fundamental epistemic principles:
- *"Don't trust the claim. Verify what the available runtime evidence supports."*
- *"Absence of evidence is not evidence of absence. Never convert missing evidence into zero or success."*
- *"Never label an inferred or assumed result as observed."*

### Test Suite Execution Summary

- **Initial Repository Baseline (Commit `077866f`):** 191 passing tests (115 baseline + 51 Phase 1–3 audit tests + 25 Phase 4 tests).
- **Adversarial Regression Test Suite Added:** 8 dedicated adversarial tests in `tests/test_phase4_adversarial_audit.py`.
- **Post-Remediation Test Results:** **199 passing tests**, 0 failures, 3 non-blocking framework deprecation warnings.
- **Test Command:** `python -m pytest tests/ -q --tb=short`
- **Execution Time:** ~11.3 seconds.

```text
........................................................................ [ 36%]
........................................................................ [ 72%]
.......................................................                  [100%]
199 passed, 3 warnings in 11.27s
```

### Final Acceptance Verdict: PASS WITH CONDITIONS

All confirmed vulnerabilities and mathematical correctness defects discovered during adversarial inspection (ADV-001 through ADV-007) have been completely remediated, with passing regression tests.

**Conditions:**
1. **Tenant Authentication & Authorization (L-001):** As established in the Phase 1–3 audit, tenant isolation remains unverified and unimplemented. Local single-tenant execution does not establish tenant isolation. **The deployment blocker on public/multi-tenant deployment is strictly preserved.**
2. **Source Authenticity vs. Integrity:** Manifest SHA-256 verification proves internal bundle consistency, but does not prove source authenticity or non-repudiation without an external asymmetric digital signature (`manifest.sig`).

---

## 2. Adversarial Review of Claim Verification

Inspected `app/evidence/claim_matrix.py`, `app/epistemic/claims.py`, epistemic verdict models, and confidence bounds.

### Findings & Verified Behaviors

1. **Handling of Missing/Unknown Evidence (ADV-001 - Fixed):**
   - *Vulnerability:* When `evidence.value` was `None` (uninstrumented metric), the verifier fell back to `0.0`. On `<= target` claims (e.g. Cost per Task <= $0.10, or P95 Latency <= 500ms), this returned `VERIFIED`.
   - *Fix:* `evaluate_single_claim` strictly inspects `evidence.value` and `evidence.bounds`. If values are `None` or `evidence.tag == EpistemicTag.UNKNOWN`, it unconditionally returns `INSUFFICIENT_EVIDENCE`.
2. **Tolerance Math on Non-Percentage Dimensions (ADV-004 - Fixed):**
   - *Vulnerability:* For `GREATER_EQUAL` claims, tolerances were evaluated as `abs(claim.target_value - val) <= claim.tolerance_pct`. For a target of `0.50` (ratio) with `5%` tolerance, an observed value of `0.0` was granted `PARTIALLY_VERIFIED` because `0.50 <= 5.0`.
   - *Fix:* Relative percentage shortfalls `(abs(diff) / abs(target)) * 100 <= tol` are calculated for non-percentage metrics, correctly producing `CONTRADICTED`.
3. **Epistemic Trust Levels (T0 vs T1–T3):**
   - Stated vendor claims (`T0_SELF_REPORTED`) cannot satisfy claims requiring empirical runtime verification. `evaluate_single_claim` confirms `min_trust_level` thresholds (e.g., claims requiring `T1` or `T2` fail with `INSUFFICIENT_EVIDENCE` if only `T0` evidence exists).
4. **Dark-Zone Autonomy Thresholds (35% Rule):**
   - Validated that systems exhibiting `> 35%` unobserved/dark-zone spans are capped at `EpistemicTag.UNKNOWN` or `PARTIALLY_VERIFIED` with widened intervals, never reaching full `VERIFIED` status.
5. **Sample-Size Thresholds:**
   - Evaluated under small-sample conditions ($N < 10$). The system accurately flags sample size warnings and widens confidence intervals, preventing unwarranted certainty.
6. **Determinism:**
   - Identical claim schemas and evidence values produce bit-identical `ClaimEvaluationResult` objects across all invocations.

---

## 3. Evidence Provenance & Manifest Integrity Audit

Inspected `app/reporting/manifest.py`, bundle compiler, and canonicalization algorithms.

### Findings & Verified Behaviors

1. **Manifest Path Traversal & Escaping (ADV-002 - Fixed):**
   - *Vulnerability:* `verify_bundle_integrity()` permitted relative paths containing `..` or absolute paths (`/etc/passwd`, `C:\Windows\win.ini`), escaping the bundle root.
   - *Fix:* Manifest verification strictly verifies that every declared artifact path is relative, contains no `..` segments, and resolves within the canonical `bundle_root` via `os.path.commonpath`.
2. **Duplicate Artifact Paths (ADV-005 - Fixed):**
   - *Vulnerability:* Duplicate artifact entries in `manifest.json` incremented verified file counts multiple times, allowing incomplete bundles to appear verified.
   - *Fix:* Duplicate paths are flagged immediately, returning `VerificationStatus.CORRUPTED_BUNDLE`.
3. **Canonicalization & Hash Verification:**
   - Structured JSON artifacts are serialized via RFC 8785 canonical JSON (`separators=(',', ':')`, `sort_keys=True`, UTF-8 encoded).
   - Raw byte payloads (e.g., OTLP trace bytes) are hashed directly without transformation.
   - Recomputing hashes over modified artifacts immediately produces `VerificationStatus.INTEGRITY_VIOLATION`.
4. **Trust Model Distinction (Integrity vs. Authenticity):**
   - The manifest establishes **internal cryptographic integrity** (files have not been altered since the manifest was created).
   - **Crucial Distinction:** An attacker who alters an artifact and regenerates `manifest.json` will pass integrity verification. The manifest does *not* provide non-repudiation or author authenticity without an asymmetric digital signature (`manifest.sig`) signed by an accredited auditor's private key.

---

## 4. API & CLI Security Audit

Inspected `app/api/routes.py` and `cli.py`.

### Findings & Verified Behaviors

1. **Directory Traversal in `POST /api/v1/bundles/verify` (ADV-007 - Fixed):**
   - *Vulnerability:* The endpoint accepted arbitrary `bundle_dir` strings without path sanitization, enabling callers to point the verifier to arbitrary host paths.
   - *Fix:* Enforced path normalization, traversal rejection, and containment validation within application bundle roots. Violations return `HTTP 400 Bad Request`.
2. **Company Scope & Evidence Isolation:**
   - Bundle exports filter strictly by `company_id`. No cross-company evidence leakage was observed within database queries.
   - CLI commands (`verify-bundle`, `export-aibom`, `generate-report`) operate with identical path validation and verification semantics as the HTTP endpoints.
3. **Tenant Authentication Blocker (L-001):**
   - Endpoints do not verify caller identity or tenancy. While safe for isolated local auditing, this remains an absolute blocker for multi-tenant deployment.

---

## 5. Canonical Reports Audit

Inspected `app/reporting/canonical_report.py` and `app/reporting/service.py`.

### Findings & Verified Behaviors

1. **JSON vs. Markdown Parity:**
   - Both JSON and Markdown representations are rendered directly from the same underlying `DiligenceReport` Pydantic model.
   - Metrics, confidence bounds, sample sizes, epistemic tags, and claim matrices match exactly across formats.
2. **Preservation of Unknowns:**
   - Metrics with missing telemetry render as `UNKNOWN` or `None` in JSON, and `[UNKNOWN]` with `N/A` or widened bounds in Markdown. They are never rendered as `0` or `100%`.
3. **Synthetic Data Disclosure:**
   - Synthetic benchmark scenarios are conspicuously labeled in report headers and summaries (`is_synthetic: true`, `[SYNTHETIC SCENARIO]`). Synthetic evidence is never represented as empirical customer telemetry.
4. **Calculation & Schema Versioning:**
   - Reports embed `report_version: "1.0.0"`, `manifest_version: "1.0.0"`, and the diligence engine commit/version.

---

## 6. CycloneDX AI-BOM Audit & Schema Verification

Inspected `app/aibom/generator.py`, `app/aibom/bom-1.6.schema.json`, and `app/aibom/bom-1.5.schema.json`.

### Findings & Verified Behaviors

1. **Schema Provenance & Validation:**
   - Bundled schemas (`bom-1.6.schema.json` and `bom-1.5.schema.json`) were verified against official OWASP CycloneDX specification releases from `raw.githubusercontent.com/CycloneDX/specification`.
   - Real schema validation is executed using `jsonschema.validate()`. Both version 1.6 and 1.5 schemas validate successfully against compliant exported BOMs.
2. **HTTP Status on Schema Failure (ADV-006 - Fixed):**
   - *Vulnerability:* Validation failure previously returned HTTP 200 OK with a failure header.
   - *Fix:* The endpoint now returns `HTTP 422 Unprocessable Entity` with full validation error details.
3. **Elimination of Fabricated Components (ADV-003 - Fixed):**
   - *Vulnerability:* Native AI-BOM generator previously invented `pinecone` and `text-embedding-3-small` if any tool name contained `"rag"`.
   - *Fix:* Heuristic fabrication removed. Vector stores and frameworks are populated solely when supported by concrete span telemetry attributes (`vector_db.system`, etc.).
4. **Epistemic Labeling:**
   - CycloneDX components derived from runtime observation are tagged with evidence properties; unverified components are labeled `inferred: true` or omitted entirely.

---

## 7. Remediation Register Summary

| Finding ID | Severity | Component | Issue | Resolution |
|---|---|---|---|---|
| **ADV-001** | P0 | Claim Verifier | `value=None` converted to `0.0` yielding false `VERIFIED` | Require non-None value/bounds; emit `INSUFFICIENT_EVIDENCE` |
| **ADV-002** | P0 | Manifest | Relative `..` and absolute path traversal in bundle verification | Disallow `..`, `isabs()`, and enforce `commonpath` |
| **ADV-003** | P1 | AI-BOM | Fabricated Pinecone vector DB & hardcoded orchestrator | Extracted strictly from span telemetry; no heuristic invention |
| **ADV-004** | P1 | Claim Verifier | `GREATER_EQUAL` tolerance subtraction on non-percentage metrics | Compute relative percentage shortfall for non-percentage metrics |
| **ADV-005** | P2 | Manifest | Duplicate artifact paths incremented verified count | Reject duplicate paths as `CORRUPTED_BUNDLE` |
| **ADV-006** | P2 | API | CycloneDX validation failure returned HTTP 200 | Return HTTP 422 Unprocessable Entity with error details |
| **ADV-007** | P1 | API | Local directory traversal in `POST /api/v1/bundles/verify` | Sanitize path, reject traversal, restrict to bundle roots |

---

## 8. Final Verdict & Deployment Posture

**Status:** **PASS WITH CONDITIONS**

- **Verified:** All 199 tests pass. Claim verification math is sound. Bundles enforce strict hermetic integrity. AI-BOM generates empirically justified, schema-valid CycloneDX artifacts.
- **Preserved Blocker:** Tenant authentication and authorization (`L-001`) remain an active deployment blocker. The software is ready for local single-tenant operation, internal auditing, and CI diligence workflows, but must not be exposed to multi-tenant or untrusted network environments.
