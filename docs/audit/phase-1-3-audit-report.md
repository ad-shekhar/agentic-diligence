# Phase 1–3 Independent Technical Audit Report

**Repository:** gentic-diligence (agd)  
**Branch:** eat/phase-03-task-segmentation-metrics  
**Audit Date:** 2026-10-22  
**Auditor:** Independent Principal Software Engineer, SRE & Methodology Auditor  
**Scope:** Phase 1 (Epistemic Foundations), Phase 2 (OTel GenAI Ingestion & Normalization), Phase 3 (Task Segmentation & Metrics Engine)  
**Readiness Verdict:** **READY WITH CONDITIONS**  

---

## 1. Actual Initial Test Baseline and Final Test Results

- **Initial Audit Baseline:** 115 passing tests (Phase 1, Phase 2, and Phase 3 unit and integration tests).
- **New Adversarial / Property-Based Tests Added:** 51 tests in 	ests/test_adversarial_audit.py.
- **Final Test Suite:** 166 passing tests, 0 failures, 3 non-blocking deprecation warnings.
- **Test Execution Time:** ~15.2 seconds across all modules.

---

## 2. Architecture and Data-Flow Review

The Agentic Diligence system is built on an evidence-first architectural model:
OTel JSON Spans -> Payload Hasher (SHA-256 Provenance) -> GenAI Normalizer (v1.0 schema) -> Database / In-Memory Store -> Task Segmenter (Gap Analysis & Clustering) -> Deterministic Metrics Engine (8 signals) -> Claim Verifier (Epistemic bounds, Trust levels) -> Output Manifest & Reports.

### Epistemic Integrity Invariant
Every output metric is bound to an EpistemicValue containing:
- alue: point estimate or None
- 	ag: OBSERVED, DERIVED, INFERRED, or UNKNOWN
- 	rust_level: T0 (Unverified vendor claim), T1 (Self-reported telemetry), T2 (Third-party observed), or T3 (Cryptographically attested / hardware-isolated)
- ounds: AutonomyBounds(lower, point, upper)
- sample_size: integer trace/task count
- unknown_fraction: ratio of missing/unobserved evidence

---

## 3. Findings Ordered by Severity

| ID | Title | Severity | Status |
|---|---|---|---|
| F-001 | Epoch Sentinel Generates Spurious UNKNOWN Gap Tasks | P1 | FIXED |
| F-002 | HHI Scale Mismatch (0–1 vs 0–10,000) Between Verifier & Engine | P1 | FIXED |
| F-003 | TCR _task_is_completed Silently Asserts Completion Without Spans | P1 | FIXED |
| F-004 | status_code Hardcoded to 'OK' in API Route get_company_metrics | P2 | FIXED |
| F-005 | Sample Size Threshold Discrepancy (N<10 vs N<15) in Verifier | P1 | FIXED |
| L-001 | Absence of Authentication & Tenant Isolation | P0 (Security) | ACCEPTED (Phase 4 block) |
| L-002 | Partial Ingestion Provenance Span-Level Granularity | P2 | ACCEPTED (Phase 4) |
| L-003 | Deprecation of FastAPI on_event | P3 | ACCEPTED (Phase 4) |
| L-004 | CycloneDX 1.6 Schema Validation Gap | P2 | DOCUMENTED |
| L-005 | DELTA Ground Truth HHI Scale Labeling | P2 | DOCUMENTED |
| L-006 | Zero-Cost Imputation for Unpriced Models in CPT | P2 | DOCUMENTED |

---

## 4. Confirmed Bugs and Reproduction Evidence

### F-001: Epoch Sentinel Spurious Gap Tasks
- **Reproduction:** Traces containing a missing timestamp normalized to 1970-01-01T00:00:00 followed by a span in 2026 produced a 56-year time gap, triggering the gap threshold and injecting phantom UNKNOWN tasks.
- **Evidence:** segment_trace() returned 	otal_tasks=2 with 1 UNKNOWN task for a single real span.
- **Resolution:** Pre-filtering epoch sentinels prior to clustering and logging explicit disclosures in 
esult.notes.

### F-002: HHI Scale Inconsistency
- **Reproduction:** Verifier checked hhi_score >= 0.80, but the metrics engine emitted values up to 10,000. Any multi-provider distribution with HHI > 1.0 (e.g., 6,000) was erroneously marked CONTRADICTED.
- **Evidence:** Balanced 60/40 distributions produced CONTRADICTED verdicts.
- **Resolution:** Updated verifier thresholds to 8000 and 3500 on the 10,000 point scale.

### F-003: TCR Silent Task Completion Fallback
- **Reproduction:** Tasks reconstructed without matching span IDs in ll_spans defaulted to True for completed status.
- **Evidence:** _task_is_completed(task, []) returned True for AUTONOMOUS tasks.
- **Resolution:** Enforced that at least one span must match and exhibit status_code == 'OK'.

### F-004: Hardcoded status_code='OK' in API Reconstructed Spans
- **Reproduction:** Reconstructed SchemaSpan instances in GET /companies/{id}/metrics hardcoded status_code='OK' regardless of sp.is_error.
- **Evidence:** Traces with is_error=True in SQLite returned 0% error rate.
- **Resolution:** Replaced with status_code='ERROR' if sp.is_error else 'OK'.

### F-005: Sample Size Inconsistency
- **Reproduction:** Claims evaluated with N=12 returned INSUFFICIENT_EVIDENCE in claims.py but returned an evaluation verdict in erifier.py.
- **Resolution:** Aligned minimum sample size to N=15 across both modules.

---

## 5. Mathematical Validation of Critical Metrics

### Signal 1: Autonomy
- Mathematical formulation:
  	ext{lower} = rac{	ext{autonomous}}{	ext{total}}, \quad 	ext{upper} = rac{	ext{autonomous} + 	ext{unknown}}{	ext{total}}
- **Invariant Verified:** $	ext{lower} \le 	ext{point} \le 	ext{upper}$.
- **Invariant Verified:** Adding unknown tasks strictly widens or maintains uncertainty spread ($	ext{upper} - 	ext{lower}$).

### Signal 2 & 4: Unit Economics & Cost Allocation
- Cost Per Task (CPT) strictly attributes model token pricing.
- Unknown model pricing is tagged INFERRED and flagged in disclosures.

### Signal 5: Provider Concentration (HHI)
- Mathematical formulation: $	ext{HHI} = \sum s_i^2 	imes 10,000$ where $ is provider share in $[0, 1]$.
- Validated: 100% single provider yields 10,000; equal 50/50 split yields 5,000; equal 25/25/25/25 yields 2,500.

### Signal 7: Reliability & Failure Cascades
- Error rate  = rac{	ext{error\_spans}}{	ext{total\_spans}}$.
- Task Completion Rate  = rac{	ext{completed\_tasks}}{	ext{total\_tasks}}$ requiring explicit OK telemetry.

---

## 6. Security, Privacy, and Tenant-Isolation Findings

1. **Missing Authentication (L-001, P0 Security):**
   - The API currently lacks authentication, authorization headers, and tenant boundary enforcement.
   - Anyone with network access can query any company_id.
   - **Verdict:** Accepted for development testbeds; blocks production deployment.
2. **Payload Storage & PII:**
   - OTLP ingestion retains payload bodies and prompts if present.
   - SHA-256 provenance ensures non-repudiation, but scrubbing/hashing of sensitive prompts must precede external multi-tenant deployment.

---

## 7. Determinism and Reproducibility Results

- **Reproducibility Test:** 50 repeated evaluations of identical synthetic and real-trace traces produced bit-for-bit identical JSON representations.
- **Provenance Integrity:** Ingested payloads compute SHA-256 hash immediately upon entry, logged in payload_provenance with timestamp and payload length.

---

## 8. Fixes Made and Tests Added

1. pp/analysis/task_segmentation.py: Filter epoch sentinels (F-001).
2. pp/evidence/verifier.py: Aligned HHI 0–10,000 scale (F-002) and N>=15 sample size threshold (F-005).
3. pp/analysis/metrics_engine.py: Fixed completion verification without spans (F-003).
4. pp/api/routes.py: Derived status_code from DB error flags (F-004).
5. 	ests/test_adversarial_audit.py: 51 new property-based and boundary regression tests covering all findings and invariants.

---

## 9. Known Limitations and Accepted Risks

- L-001: No Auth / Tenant Isolation (Blocking for Phase 4 deployment, acceptable for local testing).
- L-002: Ingestion partial failure reporting lacks per-span drop index.
- L-003: FastAPI on_event lifespan migration queued for Phase 4.
- L-004: CycloneDX schema validation automated check needed in CI.
- L-005: Ground truth DELTA scale naming clarification.
- L-006: Unpriced models zero-cost fallback documented in notes.

---

## 10. Phase 4 Contracts and Unresolved Decisions

Contracts formalized in docs/phase-4/data-contracts.md:
1. Claim Verification Matrix Schema (v1.0).
2. Canonical Evidence and Diligence Report Schema (v1.0).
3. Artifact Manifest Specification with SHA-256 hashes (manifest-spec.md).
4. CycloneDX AI-BOM Specification (cyclonedx-decision.md).

---

## 11. Criterion-by-Criterion Readiness Verdict

| Criterion | Requirement | Result |
|---|---|---|
| Epistemic Integrity | No silent conversions of unknowns | **PASSED** |
| Metric Mathematical Rigor | Bounds, HHI, TCR, CPT verified | **PASSED** |
| Ingestion & Provenance | SHA-256 payload audit trail | **PASSED** |
| Test Regression Suite | Baseline + Adversarial suite passing | **PASSED** (166/166 tests) |
| Multi-tenant Security | Auth, tenant isolation, RBAC | **NOT VERIFIED / NOT IMPLEMENTED** (L-001) |
| Phase 4 Data Contracts | Complete schema and manifest definitions | **PASSED** |

### Final Readiness Verdict: **READY WITH CONDITIONS**

**Conditions for Phase 4 Execution:**
1. Maintain strict preservation of the 166 passing tests as regression gate.
2. Tenant isolation and authentication must be addressed prior to any non-local deployment.
3. CycloneDX generation must follow the decisions documented in docs/phase-4/cyclonedx-decision.md.
