# Testing Strategy & Quality Assurance Plan
**Document:** `docs/phase-09/testing-strategy.md`  
**Phase:** 9 — Complete Product Workflows  

---

## 1. Testing Hierarchy & Verification Matrix

| Level | Focus Areas | Target Test Suite | Baseline Requirement |
|---|---|---|---|
| **Unit & Model Tests** | `Project`, `Assessment`, `AssessmentEngineExecution`, `Finding`, `IngestionJob`, `ProjectActivity` | `tests/test_phase9_models.py` | 100% ORM relationship & cascading constraint integrity. |
| **Project Lifecycle** | Project creation, retrieval, updates, soft archival, activity tracking | `tests/test_phase9_project_lifecycle.py` | Zero mock fallbacks; real DB records. |
| **Onboarding Paths** | Benchmark onboarding (preserves scenarios A–J) vs Custom onboarding | `tests/test_phase9_onboarding.py` | Custom target never defaults to Scenario A. |
| **Ingestion Pipeline** | File upload, format validation (.json/.jsonl), size limits, dedup, jobs | `tests/test_phase9_ingestion.py` | Byte hash non-repudiation & job history. |
| **Assessment Orchestrator** | 10-engine execution, state transitions, partial failures, error isolation | `tests/test_phase9_assessment_orchestration.py` | Engine failure isolation & finding persistence. |
| **Reporting & Bundle** | Report generation, download routes, multi-format delivery | `tests/test_phase9_reporting.py` | Canonical SHA-256 manifest validation. |
| **End-to-End User Journey** | Complete flow from project creation through assessment and report | `tests/test_phase9_e2e_journey.py` | Acceptance scenario full pass. |
| **Regression Suite** | All Phase 1–8 historical tests | `pytest tests/` | Maintain 280 passing tests with 0 regressions. |

---

## 2. Invariant Epistemic Assertions
- Epistemic verdicts (`VERIFIED`, `CONTRADICTED`, `INSUFFICIENT_EVIDENCE`) must remain mathematically bounded.
- Absence of telemetry evidence must never be converted into a successful verdict.
- Every finding must preserve an evidence link to supporting traces, spans, or cryptographic hashes.

