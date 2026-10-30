# Unified Evidence Architecture Specification (Phase 6)

## 1. Architectural Overview

Agentic Diligence Phase 6 establishes the **Unified Evidence Ingestion & Verification Pipeline**, connecting multi-source observational telemetry adapters (OTLP v1.28.0, MCP JSON-RPC 2.0, WebExtension Browser Telemetry) to the deterministic claim-verification and diligence metrics engines.

```text
       External Observability Sources
   [OTLP / OpenTelemetry]   [MCP JSON-RPC]   [Browser Extension]
              │                    │                   │
              ▼                    ▼                   ▼
    ┌────────────────────────────────────────────────────────┐
    │       Phase 5 Heterogeneous Evidence Adapters          │
    │  - Normalization to v1.28.0 Conventions                │
    │  - RFC 8785 Canonical JSON & SHA-256 Envelope          │
    │  - PII / Credential Sanitization & DOM Stripping       │
    └────────────────────────────────────────────────────────┘
                               │
                               ▼
    ┌────────────────────────────────────────────────────────┐
    │          Milestone A: Unified Evidence Registry        │
    │  - SourceType Auto-Detection (OTLP/MCP/Browser)        │
    │  - Deterministic Evidence IDs: SHA-256(src,hash,tid,sid)│
    │  - Intra & Inter-Batch Deduplication Tracking          │
    │  - SQLite PayloadProvenance Cryptographic Persistence   │
    └────────────────────────────────────────────────────────┘
                               │
                               ▼
    ┌────────────────────────────────────────────────────────┐
    │         Milestone B: Evidence Correlation Engine       │
    │  - Multi-Identifier Correlation (Trace/Span/Tool/Session)│
    │  - Causal Topological Reordering (Out-of-Order Events) │
    │  - Contradiction Resolution (T2 Precedence over T1)    │
    │  - Unresolved Tool Execution Preservation (UNKNOWN)    │
    │  - Clock Skew & Dark Zone (>30s) Anomaly Flagging      │
    │  - Strict Invariant: No Relationship Fabrication       │
    └────────────────────────────────────────────────────────┘
                               │
                               ▼
    ┌────────────────────────────────────────────────────────┐
    │     Milestone C: Unified Verification Pipeline         │
    │  - Atomic Task Segmentation (TraceSegmentationResult)  │
    │  - Deterministic Metrics Engine (8 Canonical Signals)  │
    │  - Epistemic Bounds Widening under Unknowns            │
    │  - Dark Zones > 35% -> INSUFFICIENT_EVIDENCE           │
    │  - Claim Verification Matrix (VERIFIED/CONTRADICTED/IE)│
    └────────────────────────────────────────────────────────┘
                               │
                               ▼
    ┌────────────────────────────────────────────────────────┐
    │         Milestone D: Delivery & Reproducibility        │
    │  - REST Endpoints: /api/v1/evidence/{ingest,verify,...}│
    │  - CLI Tooling: python cli.py evidence {ingest,verify} │
    │  - Reproducible Cryptographic Verification Reports     │
    └────────────────────────────────────────────────────────┘
```

---

## 2. Core Epistemic Invariants

1. **Absence of Evidence is Never Evidence of Absence:**
   Missing telemetry events or uninstrumented temporal gaps are explicitly recorded as `[UNKNOWN]`. They widen uncertainty intervals $[\text{lower}, \text{upper}]$ and never collapse into autonomous success or failure.
2. **Strict Epistemic Ceiling on Unknowns (35% Rule):**
   When uninstrumented dark zones account for $> 35\%$ of total execution tasks, the system deterministically outputs `INSUFFICIENT_EVIDENCE`.
3. **Multi-Tier Observer Precedence (T2 > T1):**
   When an in-process client self-report (Trust Level T1 OTLP) conflicts with an out-of-band proxy observation (Trust Level T2 MCP JSON-RPC), the T2 observer takes precedence. An OTLP span reporting `SUCCESS` that corresponds to an MCP JSON-RPC `error` is downgraded to `ERROR`.
4. **Human Intervention Non-Erasability:**
   If any certified adapter (e.g. Browser extension capturing an approval modal click or user override) records explicit human participation, the tool execution is flagged as `is_human_intervention = True`, preventing false autonomous claims.
5. **No Relationship Fabrication:**
   Telemetry observations lacking valid correlation keys (`trace_id`, `tool_call_id`) are placed into quarantined, unlinked traces (`unlinked-{evidence_id}`) rather than artificially merged into existing traces.

---

## 3. Data Flow & Contract Specifications

### 3.1 Deterministic Evidence ID
Every span registered in the `UnifiedEvidenceRegistry` receives a deterministic SHA-256 identifier calculated over RFC 8785 canonical keys:
$$\text{Evidence ID} = \text{SHA256}(\text{source\_type} \parallel \text{provenance\_hash} \parallel \text{trace\_id} \parallel \text{span\_id})$$

### 3.2 Correlated Tool Execution Record (`CorrelatedToolCall`)
```json
{
  "tool_call_id": "call-101",
  "tool_name": "db_query",
  "trace_id": "trace-corp-01",
  "reconciled_status": "ERROR",
  "is_human_intervention": false,
  "epistemic_tag": "[OBSERVED]",
  "trust_level": "T2",
  "sources": ["mcp", "otlp"],
  "contradiction_notes": "Contradiction on tool call call-101: T1 OTLP reported SUCCESS, but T2 MCP proxy observed JSON-RPC execution ERROR. Downgrading to ERROR."
}
```

### 3.3 REST API Endpoints
- `POST /api/v1/evidence/ingest`: Accepts multi-source payload and returns `IngestionReceipt`.
- `POST /api/v1/evidence/verify`: Accepts list of `ClaimSchema`s and returns `VerificationPipelineResult`.
- `GET /api/v1/evidence/records`: Queries registered records filtered by `company_id`, `trace_id`, `source_type`.
- `GET /api/v1/evidence/provenance`: Returns registered `ProvenanceEnvelope`s and cryptographic digests.

