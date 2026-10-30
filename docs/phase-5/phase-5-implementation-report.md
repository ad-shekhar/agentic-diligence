# Phase 5 Implementation Report: Evidence-Adapter Architecture, Ground-Truth Pilots & Protocol Extensions

**Version:** 1.0.0  
**Branch:** `feat/phase-05-ground-truth-mcp-extensions`  
**Date:** 2026-10-30  
**Status:** **PASS**  
**Previous Baseline:** 199 passing tests  
**Final Test Result:** **229 passing tests (100% pass rate, 0 failures)**  

---

## 1. Overview & Architectural Motivation

Phase 5 extends Agentic Diligence (`agd`) from a single-channel OpenTelemetry receiver to a generalized, multi-source Evidence-Adapter Architecture. Modern agentic runtimes execute across heterogeneous environments:
- In-process framework loops (LangChain, LangGraph, AutoGen)
- Out-of-band protocols (Model Context Protocol / MCP clients and tool servers)
- Browser automation agents (WebExtensions and DOM sandboxes)

Phase 5 addresses these topologies without fragmenting the deterministic analysis core. All sources are normalized into the universal [`NormalizedSpan`](file:///c:/Users/adity/agentic-diligence/app/ingestion/schema.py) and wrapped in a cryptographic [`ProvenanceEnvelope`](file:///c:/Users/adity/agentic-diligence/app/adapters/base.py) before feeding into the unchanged downstream task segmentation, metrics calculation, claim verification, and manifest signing pipelines.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        PHASE 5 EVIDENCE ADAPTERS                       │
├─────────────────────┬───────────────────────────┬──────────────────────┤
│ OtlpEvidenceAdapter │    McpEvidenceAdapter     │BrowserEvidenceAdapter│
│ (OTel GenAI v1.28)  │  (MCP JSON-RPC stdio/SSE) │  (WebExtension DOM)  │
└──────────┬──────────┴─────────────┬─────────────┴──────────┬───────────┘
           │                        │                        │
           ▼                        ▼                        ▼
┌────────────────────────────────────────────────────────────────────────┐
│                 Universal ProvenanceEnvelope (RFC 8785)                │
│                 Canonical NormalizedSpan Stream                        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│              Deterministic Downstream Diligence Pipeline               │
│  - Task Segmentation (app/analysis/task_segmentation.py)               │
│  - 8-Signal Metrics Engine (app/analysis/metrics_engine.py)            │
│  - Claim Verification Matrix (app/evidence/claim_matrix.py)            │
│  - Canonical Reports & CycloneDX AI-BOM (app/reporting/)              │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Delivered Milestones & Components

### Milestone B: Architecture Specification (`docs/phase-5/evidence-adapter-architecture.md`)
- Formalized universal abstract interface [`BaseEvidenceAdapter`](file:///c:/Users/adity/agentic-diligence/app/adapters/base.py).
- Defined [`ProvenanceEnvelope`](file:///c:/Users/adity/agentic-diligence/app/adapters/base.py) with RFC 8785 canonical JSON serialization and SHA-256 integrity digest.
- Formalized cross-source capability disclosure matrix and blind-spot registry.
- Established strict 6-state MCP lifecycle disambiguation model.

### Milestone C: Ground-Truth Controlled Pilot (`app/adapters/pilot.py`)
- Implemented 7 deterministic runtime scenarios ($N = 20$ traces each, 140 traces evaluated):
  1. **Autonomous Tool Completion:** 100% autonomous, 0% error rate $\to$ verified.
  2. **Human Intervention:** Explicit approval checkpoint $\to$ 100% HIR, 0% autonomy.
  3. **Tool Failure and Retry:** Transient 504 gateway timeout recovering on secondary retry.
  4. **Complete Failure:** Unrecoverable database deadlock and task abort.
  5. **Suppressed Telemetry (Dark Zone):** Uninstrumented gaps $> 30\text{s}$ creating $> 35\%$ unknown tasks $\to$ enforces mandatory `INSUFFICIENT_EVIDENCE` verdict (prevents false positives).
  6. **Duplicate Events:** Network retry duplicates filtered at adapter layer without double-counting tokens or task costs.
  7. **Provider Fallback:** OpenAI 429 rate limit triggers Anthropic Claude fallback, demonstrating verified HHI provider diversification ($HHI \le 6000$).
- **Empirical Diligence Verification Metrics:**
  - **False-Positive Verification Rate (FPVR):** **0.0%** (Zero false claims verified).
  - **False-Negative Verification Rate (FNVR):** **0.0%** (Zero true claims falsely contradicted).
  - **Verification Accuracy:** **100.0%** across all 13 ground-truth claim evaluations.

### Milestone D: Model Context Protocol Adapter (`app/adapters/mcp.py`)
- Standard JSON-RPC 2.0 parser supporting stdio and HTTP SSE message streams.
- Disambiguates tool discovery (`tools/list`), call requests (`tools/call`), and results.
- **Epistemic Invariant Enforced:** An unanswered `tools/call` without matching server response is mapped to `tool_status="UNKNOWN"` and `epistemic_tag=EpistemicTag.UNKNOWN`, widening autonomy bounds instead of falsely assuming completion or failure.
- Seamlessly integrates with [`segment_trace()`](file:///c:/Users/adity/agentic-diligence/app/analysis/task_segmentation.py).

### Milestone E: Browser Extension Adapter & Privacy Redaction (`app/adapters/browser.py`)
- Prototype WebExtension action adapter mapping browser DOM interactions and modal confirmations.
- **Zero-Leakage Privacy Engine:**
  - Completely strips full DOM trees, outerHTML, and raw HTML dumps.
  - Automatically scrubs credit card numbers (`\b(?:\d[ -]*?){13,16}\b`), Bearer tokens, passwords, and API keys.
  - Transparently records scrubbed fields in `ProvenanceEnvelope.redacted_fields`.
- Maps approval modals (`approval_modal_confirm` / `approval_modal_reject`) directly to `is_human_intervention=True` with `OBSERVED_TELEMETRY`.

---

## 3. Test Suite & Verification Summary

| Test Module | Coverage Scope | Tests Passed |
| :--- | :--- | :---: |
| [`tests/test_adapter_contract.py`](file:///c:/Users/adity/agentic-diligence/tests/test_adapter_contract.py) | `ProvenanceEnvelope` serialization, SHA-256 reproducibility, 10MB limits, OTLP reference adapter | **10** |
| [`tests/test_ground_truth_pilot.py`](file:///c:/Users/adity/agentic-diligence/tests/test_ground_truth_pilot.py) | 7 deterministic pilot scenarios, confusion matrix, FPVR == 0.0%, FNVR <= 5.0% | **8** |
| [`tests/test_mcp_adapter.py`](file:///c:/Users/adity/agentic-diligence/tests/test_mcp_adapter.py) | MCP JSON-RPC protocol, tool discovery, unanswered timeout invariant, task segmentation integration | **8** |
| [`tests/test_browser_adapter.py`](file:///c:/Users/adity/agentic-diligence/tests/test_browser_adapter.py) | WebExtension action normalization, DOM stripping, credential redaction, approval modal HITL mapping | **4** |
| Existing Regression Baseline (Phase 1–4.5) | Ingestion, normalizer, segmentation, metrics, claim matrix, manifests, reports, CycloneDX 1.6, adversarial audit | **199** |
| **Total Test Suite** | **Entire repository** | **229 passed** (0 failures) |

---

## 4. Key Epistemic Invariants Maintained

1. **"Don't trust the claim. Verify what the available runtime evidence supports."**
   - Stated claims are evaluated strictly against bounded mathematical evidence intervals.
2. **"Absence of evidence is not evidence of absence."**
   - Unanswered MCP tool calls and unobserved browser intervals yield explicit `[UNKNOWN]` markers that widen confidence bounds rather than collapsing into success.
3. **"Never label an inferred or assumed result as observed."**
   - Inferred latency heuristics carry `[INFERRED]` tags; only explicit telemetry spans receive `[OBSERVED]`.
4. **"Zero False Positives (FPVR = 0.0%)."**
   - Unfounded, exaggerated, or dark-zone claims are consistently rejected with `CONTRADICTED` or `INSUFFICIENT_EVIDENCE`.

