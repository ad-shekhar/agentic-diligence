# Ingestion Workflow & Evidence Management Architecture
**Document:** `docs/phase-09/ingestion-workflow.md`  
**Phase:** 9 — Complete Product Workflows  

---

## 1. End-to-End Ingestion Pipeline

```mermaid
sequenceDiagram
    autonumber
    actor User as Auditor / Engineer
    participant UI as Ingestion Modal / Evidence View
    participant API as POST /api/v1/projects/{id}/ingest
    participant Hash as Pre-Parsing SHA-256 Engine
    participant Dedup as Duplicate Detection
    participant Norm as OTel GenAI Normalizer
    participant DB as SQLite Relational Store

    User->>UI: Select or Drag & Drop File (.json / .jsonl)
    UI->>UI: Validate format & file size (<= 25MB)
    UI->>API: Multipart upload or JSON payload
    API->>Hash: Compute SHA-256 of raw incoming byte stream
    Hash-->>API: payload_hash
    API->>Dedup: Query PayloadProvenance by payload_hash
    alt Duplicate Detected
        Dedup-->>API: Duplicate Found
        API-->>UI: 200 OK (Status: DUPLICATE, Spans already anchored)
    else Unique Payload
        API->>Norm: Parse & Normalize Spans (v1.28.0)
        Norm-->>API: NormalizedSpans & CostEvents
        API->>DB: Store Traces, Spans, CostEvents, PayloadProvenance
        API->>DB: Record IngestionJob & ProjectActivity
        DB-->>API: Success Confirmation
        API-->>UI: 200 OK (Status: SUCCESS, Spans Count, Hash)
        UI-->>User: Success toast & real-time trace count refresh
    end
```

---

## 2. Ingestion Security & Data Integrity Controls

1. **Pre-Parsing Non-Repudiation:** Byte-level SHA-256 fingerprinting ensures evidence provenance cannot be tampered with after receipt.
2. **Path Traversal & Safe Filenames:** Uploaded filenames are sanitized (`os.path.basename` + strict regex `[a-zA-Z0-9_.-]`), preventing directory traversal (`../`).
3. **Hermetic Memory Containment:** Maximum batch size enforced at 25MB; streaming chunk parser prevents denial-of-service via unbounded payloads.
4. **Credential Scrubbing:** Pre-ingestion sanitizer scrubs incoming Authorization tokens, `sk-...` API keys, and private tokens from span attributes.
