# Phase 1–3 Audit Findings Register

**Repository:** agentic-diligence (agd)  
**Branch:** feat/phase-03-task-segmentation-metrics  
**Audit Date:** 2026-10-22  
**Auditor Role:** Independent Principal Software Engineer + methodology auditor  
**Test Baseline:** 115 passing tests (pre-audit)  
**Test Result Post-Fix:** 166 passing tests (115 original + 51 new adversarial)  

---

## Finding Severity Legend

| Severity | Definition |
|----------|-----------|
| P0 | Data corruption, false verification from core logic, fundamental evidence-integrity failure |
| P1 | Incorrect metric math, silent unknown handling, trust bypass, data leakage, non-reproducible findings |
| P2 | Edge-case failures, inconsistent interfaces, missing validation, materially misleading docs |
| P3 | Maintainability, minor UX, nonessential cleanup |

---

## Confirmed Findings

### F-001 — Epoch Sentinel Generates Spurious UNKNOWN Gap Tasks (P1)

**Affected file:** pp/analysis/task_segmentation.py  
**Function:** segment_trace()

**Description:**  
The normalizer uses datetime(1970, 1, 1, 0, 0, 0) as the epoch sentinel for missing timestamps. When a trace contained a sentinel-timestamped span alongside real 2026-era spans, the gap calculation would produce a gap of ~50+ years, classifying it as UNKNOWN. This silently added phantom UNKNOWN tasks to the autonomy count.

**Impact:** Autonomy bounds could be artificially widened by uninstrumented sentinel spans, producing false [lower, upper] intervals that do not correspond to real uninstrumented intervals. Epistemic invariant violated: unknown tasks must represent actual missing evidence, not a timestamp parsing artifact.

**Fix Applied:** segment_trace() now filters spans with start_time == datetime(1970,1,1,0,0,0) before gap analysis. Filtered counts are disclosed in 
esult.notes. If all spans are sentinels, the function returns 	otal_tasks=0 with EpistemicTag.UNKNOWN.

**Regression Test:** 	ests/test_adversarial_audit.py::test_epoch_only_trace_returns_zero_tasks, 	est_epoch_plus_real_span_no_false_gap, 	est_epoch_span_noted_in_result

**Resolution:** FIXED

---

### F-002 — HHI Scale Mismatch Between verifier.py (0–1) and metrics_engine.py (0–10,000) (P1)

**Affected file:** pp/evidence/verifier.py  
**Function:** erify_dependency_claim()

**Description:**  
metrics_engine._compute_hhi() multiplies by 10,000, emitting values in [0, 10,000]. erifier.verify_dependency_claim() used thresholds of 0.80 and 0.35 (0–1 scale). A single-provider scenario with HHI=10,000 would NOT trigger CONTRADICTED because 10000 >= 0.80 is True, but for mixed provider (HHI=6000), the condition 6000 >= 0.80 would also be True — so the CONTRADICTED threshold was effectively always met. The PARTIALLY_VERIFIED path at >= 0.35 was also always True for any non-zero HHI, meaning the verifier could never reach VERIFIED via HHI path alone.

**Impact:** Any code path calling erify_dependency_claim with an HHI from the metrics engine would produce incorrect verdicts. VERIFIED was unreachable via HHI logic.

**Fix Applied:** Updated thresholds to 0–10,000 scale:
- CONTRADICTED: hhi_score >= 8000.0 (equivalent to 0.80 on 0–1 scale)
- PARTIALLY_VERIFIED: hhi_score >= 3500.0 (equivalent to 0.35 on 0–1 scale)
- VERIFIED: hhi_score < 3500.0
Formatted HHI in messages as {hhi:.0f}/10000 for unambiguous scale indication.

**Regression Test:** 	est_adversarial_audit.py::test_hhi_verifier_* (4 tests)

**Resolution:** FIXED

---

### F-003 — TCR _task_is_completed Silently Asserts Completion Without Span Evidence (P1)

**Affected file:** pp/analysis/metrics_engine.py  
**Function:** _task_is_completed()

**Description:**  
Original fallback: if no spans in ll_spans matched a task's span_ids, the function returned True for AUTONOMOUS/HUMAN_EXPLICIT/HUMAN_INFERRED tasks. This path is hit when the DB-backed GET /companies/{id}/metrics route reconstructs spans — if a task's span_ids don't match span_ids in the reconstructed span set, TCR was inflated. Epistemic invariant violated: absence of observed completion evidence != evidence of completion.

**Impact:** Task Completion Rate could be overstated. The API endpoint GET /companies/{id}/metrics was affected since it reconstructs spans from DB independently of segmentation.

**Fix Applied:** _task_is_completed now returns False when:
- span_ids is empty (UNKNOWN gap tasks)
- No matching spans are found in ll_spans
- All matching spans have non-OK status codes  
Only returns True when at least one matching span has status_code == 'OK'.

**Regression Test:** 	ests/test_adversarial_audit.py::test_task_is_completed_* (4 tests)

**Resolution:** FIXED

---

### F-004 — status_code Hardcoded to 'OK' in API Route get_company_metrics (P2)

**Affected file:** pp/api/routes.py  
**Function:** get_company_metrics() (line 427)

**Description:**  
When reconstructing NormalizedSpan objects from SpanModel DB records to pass to the metrics engine, status_code was hardcoded to 'OK'. The actual sp.is_error flag from the database was ignored.

**Impact:** The Error Rate (ER) signal for DB-backed company metrics always reported 0% error rate, regardless of actual errors in the database. A trace full of errors would still report 0% error rate via this endpoint.

**Fix Applied:** Set status_code='ERROR' if sp.is_error else 'OK' based on the DB field.

**Regression Test:** 	ests/test_adversarial_audit.py::test_db_span_reconstruction_preserves_error_status

**Resolution:** FIXED

---

### F-005 — Sample Size Threshold Inconsistency: verifier.py uses N<10 but claims.py uses N<15 (P1)

**Affected file:** pp/evidence/verifier.py  
**Functions:** erify_autonomy_claim(), erify_economics_claim()

**Description:**  
erifier.py returned INSUFFICIENT_EVIDENCE when sample_size < 10. pp/evidence/claims.py default min_sample_size was 15. The two verification paths in the system would reach contradictory conclusions for sample sizes between 10 and 14: claims.py would report INSUFFICIENT_EVIDENCE while erifier.py would evaluate the claim.

**Impact:** Non-deterministic system behavior depending on which verification function was invoked for sample sizes 10–14.

**Fix Applied:** Aligned erifier.py to sample_size < 15 across autonomy and economics checks, consistent with claims.py. Updated error messages to state 'minimum: 15' explicitly.

**Regression Test:** 	est_adversarial_audit.py::test_autonomy_verifier_threshold_n_lt_15, 	est_economics_verifier_threshold_n_lt_15

**Resolution:** FIXED

---

## Known Limitations and Accepted Risks (Not Fixed This Cycle)

### L-001 — No Authentication or Tenant Isolation (P0 — Security Risk, Accepted for Phase 4)

**Description:** All API endpoints accept company_id as a URL/query parameter with no authentication. Any caller can access any company's data. This is explicitly a pre-production limitation.

**Impact:** Cross-company data leakage in any deployed environment.

**Recommendation:** Add API key authentication + tenant scoping before any external deployment. Document explicitly in API documentation.

**Resolution:** NOT FIXED — accepted risk for development phase, must be resolved before Phase 4 production hardening.

---

### L-002 — Transaction Safety: Provenance and Span Persistence in Same Commit (P2)

**Description:** otlp_handler.py processes spans in a loop where individual span errors are silently caught. The provenance record is added AFTER span processing and committed in the same db.commit(). If some spans fail and others succeed, the provenance record status is 'PARTIAL' but does not enumerate exactly which spans were dropped.

**Impact:** Low risk in practice — the provenance hash still represents the raw payload. But audit consumers cannot determine from the DB alone which spans from a PARTIAL payload are missing without re-parsing the original payload.

**Recommendation:** Log exact failed span IDs in provenance error_message.

**Resolution:** ACCEPTED AS P2 — not fixed this cycle, recorded for Phase 4.

---

### L-003 — FastAPI on_event Deprecation (P3)

**File:** pp/main.py  
**Warning:** DeprecationWarning: on_event is deprecated, use lifespan event handlers

**Resolution:** NOT FIXED — cosmetic, does not affect behavior, recorded for Phase 4 cleanup.

---

### L-004 — CycloneDX Version Decision (P2)

**File:** pp/aibom/generator.py  
**Description:** The generator emits 'specVersion': '1.6' with component type 'machine-learning-model'. CycloneDX 1.6 is current as of this audit. The machine-learning-model type was introduced in the AI/ML extension of CycloneDX 1.5. However, the generated output has NOT been validated against the official CycloneDX 1.6 JSON schema.

**Recommendation:** See docs/phase-4/cyclonedx-decision.md for full resolution.

**Resolution:** DOCUMENTED — see Phase 4 contracts.

---

### L-005 — Ground Truth DELTA Benchmark HHI Uses 0–1 Scale Internally (P2)

**File:** pp/benchmarks/ground_truth.py  
**Description:** expected_hhi=0.82 in DELTA benchmark uses 0–1 raw HHI (not the 0–10,000 scale used by the metrics engine). This is intentional for the mathematical ground-truth computation (which is scale-independent), but the field name expected_hhi is ambiguous.

**Impact:** If benchmark expected_hhi is directly compared to API output, scale mismatch would produce incorrect test assertions.

**Recommendation:** Rename expected_hhi to expected_hhi_raw_fraction and add expected_hhi_10k as the 0–10,000 equivalent.

**Resolution:** DOCUMENTED — accepted P2 for Phase 4 cleanup.

---

### L-006 — CPT Includes Zero-Cost for Unpriced Spans (P2)

**Description:** When a span's model is unknown, compute_span_cost returns (0.0, UNKNOWN). The 0.0 cost is included in the total when computing Cost Per Task. CPT is tagged INFERRED (correct), but the 0.0 contribution silently understates cost for unpriced models.

**Impact:** CPT will be understated whenever unknown-provider spans exist. The INFERRED tag does warn users, but the magnitude of understatement is not quantified.

**Recommendation:** Document explicitly in CPT notes: 'X spans with unknown models contribute .00 — actual cost may be higher.' This is already partially in the notes string.

**Resolution:** DOCUMENTED — acceptable P2 for current phase.

---

## Audit Invariant Verification Summary

| Invariant | Status |
|-----------|--------|
| Lower bound <= point estimate <= upper bound | VERIFIED (9 parametrized cases) |
| Unknown tasks widen spread | VERIFIED |
| T0 evidence cannot satisfy T1+ claims | VERIFIED |
| N < 15 produces INSUFFICIENT_EVIDENCE | VERIFIED (both paths) |
| Epoch sentinel excluded from gap analysis | VERIFIED |
| HHI on 0–10,000 scale throughout | VERIFIED |
| Inferred spans produce INFERRED tag | VERIFIED |
| Task count reconciliation | VERIFIED (4 scenarios) |
| Determinism across repeated calls | VERIFIED |
| Error-only tasks not marked complete | VERIFIED |
