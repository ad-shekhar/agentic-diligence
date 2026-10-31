# Agentic Diligence — Phase 7.1 Implementation Report
**Security, Persistence & Concurrency Foundation**

- **Date:** October 31, 2026
- **Status:** COMPLETED & VERIFIED
- **Working Branch:** `feat/phase-07.1-security-persistence-concurrency`
- **Target Release:** Phase 7.1 Foundation
- **Test Suite Status:** 268 passed, 3 deprecation warnings, 0 failures (100% pass rate)

---

## 1. Executive Summary

Phase 7.1 resolves all three high-severity P0 architectural blockers identified during the Phase 7 technical audit:

1. **P0-A (Unauthenticated REST Endpoints):** Established a centralized service-to-service API key authentication and tenant authorization boundary over `/api/v1/evidence/*`. Every request is authenticated against hashed credentials (`key_hash`) and authorized at the company and tenant level, eliminating cross-tenant data leakage and unauthorized telemetry poisoning.
2. **P0-B (Volatile In-Memory Evidence Registry):** Replaced volatile in-memory dictionary-only storage with a durable relational schema (`durable_evidence_records`) backed by SQLite WAL. Historical evidence records, normalized spans, envelopes, and deduplication states persist across process restarts and transparently hydrate on demand.
3. **P0-C (Registry Concurrency Safety):** Protected all `UnifiedEvidenceRegistry` mutations and lookups with re-entrant synchronization (`threading.RLock`) and reconfigured SQLite with Write-Ahead Logging (`PRAGMA journal_mode=WAL;`), `PRAGMA synchronous=NORMAL;`, and a 30-second lock timeout to eliminate write contention and race conditions under multi-threaded ingestion workloads.

All 257 baseline Phase 6 tests continue to pass without regression, and 11 new integration tests were added in `tests/test_phase71_security_persistence_concurrency.py`, bringing the total verified suite to **268 passing tests**.

---

## 2. Milestone A: Authentication & Tenant Authorization Architecture

### 2.1 Threat Model & Design Rationale
Prior to Phase 7.1, the evidence ingestion and verification endpoints (`/api/v1/evidence/ingest`, `/api/v1/evidence/verify`, `/api/v1/evidence/records`, `/api/v1/evidence/provenance`) accepted unauthenticated requests and relied entirely on unverified `company_id` query/body parameters. This exposed the platform to:
- Evidence poisoning by unauthorized third parties.
- Cross-tenant data leakage where tenant A could query or verify claims against tenant B's proprietary traces.
- Lack of accountability and audit trail for evidence registration.

### 2.2 Relational Model: `TenantApiKey`
Authentication credentials are modeled in `app/db/models.py` via `TenantApiKey`:

```python
class TenantApiKey(Base):
    __tablename__ = "tenant_api_keys"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    key_prefix = Column(String(16), nullable=False, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False, default="Default API Key")
    is_active = Column(Boolean, default=True, nullable=False)
    allowed_scopes = Column(String(255), default="evidence:read,evidence:write", nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
```

**Security Invariants:**
- **No Plaintext Storage:** Plaintext API keys (`agd_live_<48 hex chars>`) are generated via `secrets.token_hex(24)` and displayed once. The database stores only the SHA-256 digest (`key_hash`).
- **Non-sensitive Prefix:** `key_prefix` (first 12 characters, e.g., `agd_live_a1b2`) allows rapid lookup and safe display in logs and administrative dashboards.
- **Hierarchical Scoping:** Keys can be scoped to a single `company_id` or tenant-wide (`company_id = None`), granting access to all companies belonging to that tenant.
- **Granular Scopes:** Supported permissions include `evidence:read`, `evidence:write`, and `admin`.

### 2.3 Dependency Enforcement: `get_authenticated_context`
Centralized FastAPI dependency in `app/security/auth.py`:
- Inspects `X-API-Key` or `Authorization: Bearer <key>`.
- Rejects missing credentials with `401 Unauthorized` (`WWW-Authenticate: ApiKey`).
- Queries `TenantApiKey` using `hashlib.sha256(raw_key).hexdigest()`.
- Verifies `is_active` flag and checks expiration timestamps.
- Updates `last_used_at` non-blockingly.
- Enforces tenant isolation via `auth_context.can_access_company(target_company_id, db)`. Requests targeting an unassociated company return `403 Forbidden`.

---

## 3. Milestone B: Durable Relational Persistence & Cold-Start Hydration

### 3.1 Relational Model: `DurableEvidenceRecord`
To guarantee that telemetry evidence survives server restarts and crashes, evidence records are stored in the SQLite database via `DurableEvidenceRecord`:

```python
class DurableEvidenceRecord(Base):
    __tablename__ = "durable_evidence_records"

    evidence_id = Column(String(128), primary_key=True)
    company_id = Column(String(64), nullable=False, index=True)
    source_type = Column(String(20), nullable=False, index=True)
    adapter_id = Column(String(100), nullable=False)
    adapter_version = Column(String(50), nullable=False)
    provenance_hash = Column(String(64), nullable=False, index=True)
    trace_id = Column(String(128), nullable=False, index=True)
    span_id = Column(String(128), nullable=False)
    parent_span_id = Column(String(128), nullable=True)
    name = Column(String(255), nullable=False)
    event_timestamp_utc = Column(DateTime, nullable=False, index=True)
    ingested_at_utc = Column(DateTime, default=utc_now, nullable=False)
    trust_level = Column(String(20), nullable=False)
    epistemic_tag = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)
    conflict_details = Column(JSON, nullable=True)
    span_json = Column(JSON, nullable=False)
    envelope_json = Column(JSON, nullable=False)
```

**Compound Indexes:**
- `ix_durable_evidence_lookup`: `(company_id, source_type, trace_id, span_id)` for $O(1)$ duplicate checking.
- `ix_durable_evidence_company_time`: `(company_id, event_timestamp_utc)` for fast chronologically sorted trace aggregation.

### 3.2 Bidirectional Schema Reconstruction
Added `from_dict` factory methods to `NormalizedSpan` and `ProvenanceEnvelope` to ensure zero loss of metadata (including unmapped attributes, token counts, model identifiers, blind spots, and custom metadata) during JSON serialization and deserialization.

### 3.3 Cold-Start Hydration & Deduplication Across Restarts
In `app/adapters/registry.py`:
- `register_payload`: Queries `durable_evidence_records` using compound key `(company_id, source_type, trace_id, span_id)`. Re-ingesting a trace after process restart correctly identifies `DUPLICATE` records rather than falsely recording them as new valid evidence.
- `get_records`: When in-memory cache is empty or `db` is provided, queries SQLite, converts rows to `EvidenceRecord`, populates the in-memory lookup maps, and returns normalized results.
- `get_provenance_envelopes`: Reconstructs unique `ProvenanceEnvelope` objects from persisted JSON envelopes.
- `UnifiedVerificationPipeline.verify_claims`: Accepts `db: Optional[Session] = None` and propagates it to `get_records` and `get_provenance_envelopes`, enabling verification workflows to run immediately after a cold boot.

---

## 4. Milestone C: Concurrency Synchronization & SQLite WAL

### 4.1 Thread Synchronization
Added `self._lock = threading.RLock()` to `UnifiedEvidenceRegistry`. All registry reads and writes (`register_payload`, `get_records`, `get_provenance_envelopes`, `clear`, `get_spans_by_trace`) are wrapped in `with self._lock:`, preventing race conditions during concurrent span indexing and deduplication checks.

### 4.2 SQLite WAL Configuration
In `app/db/session.py`:
- Set connection parameters: `{"check_same_thread": False, "timeout": 30.0}`.
- In `init_db()`:
  ```sql
  PRAGMA journal_mode=WAL;
  PRAGMA synchronous=NORMAL;
  ```
- **Benefits:** Write-Ahead Logging allows readers to access the database without acquiring a table lock, while writers append sequentially. The 30-second busy timeout eliminates `sqlite3.OperationalError: database is locked` errors during bursty multi-threaded batch ingestion.

---

## 5. Milestone D: Verification & Test Results

### 5.1 Test Suite Comparison

| Test Suite | Baseline (Phase 6) | Current (Phase 7.1) | Status |
|:---|:---:|:---:|:---:|
| `test_phase6_unified_pipeline.py` | 13 passed | 13 passed | PASSED |
| `test_evidence_registry.py` | 6 passed | 6 passed | PASSED |
| `test_phase71_security_persistence_concurrency.py` (NEW) | — | 11 passed | PASSED |
| Full Repository Suite | 257 passed | **268 passed** | **100% PASSED** |
| Deprecation Warnings | 3 | 3 | Expected |
| Test Failures / Errors | 0 | 0 | Clean |
| Execution Time | ~15s | ~18s | Nominal |

### 5.2 Phase 7.1 Test Cases (`test_phase71_security_persistence_concurrency.py`)

1. `test_missing_credentials_rejected_401`: Ingest, verify, records, and provenance endpoints reject unauthenticated requests with 401.
2. `test_invalid_and_revoked_key_rejected_401`: Forged keys and deactivated keys (`is_active=False`) are rejected with 401.
3. `test_expired_key_rejected_401`: Keys past `expires_at` are rejected with 401.
4. `test_bearer_authorization_header_accepted`: Verifies `Authorization: Bearer <key>` is accepted interchangeably with `X-API-Key`.
5. `test_cross_tenant_access_prevented_403`: Verifies Tenant A credentials cannot write or read Tenant B evidence.
6. `test_scope_enforcement_read_vs_write`: Verifies read-only keys cannot write (403) and write-only keys cannot read (403).
7. `test_persistence_and_cold_start_hydration`: Ingests evidence into Registry A, boots fresh Registry B with empty in-memory cache, verifies cold-start hydration and span/envelope fidelity from SQLite.
8. `test_persistent_duplicate_detection_across_restart`: Ingests a trace, clears process memory, re-ingests the same trace, verifies duplicate status is detected via SQLite.
9. `test_verification_pipeline_cold_start_from_database`: Ingests traces, boots fresh pipeline with empty in-memory state, verifies claim verification completes successfully from SQLite records alone.
10. `test_multithreaded_registry_ingestion_thread_safety`: 10 concurrent threads simultaneously ingesting 50 traces into the same registry with zero data corruption.
11. `test_concurrent_read_write_interleaving`: Reader thread queries `get_records` while writer thread concurrently registers traces under SQLite WAL without locking errors.

---

## 6. Operational & Security Considerations

1. **Key Generation & Storage:** Plaintext API keys must be delivered securely to clients and never logged in server traces. Only `key_prefix` may be logged.
2. **Key Rotation:** Rotate keys by creating a new key with the same tenant/company scope, updating client headers, and setting `is_active=False` on the retired key.
3. **Database Maintenance:** For production workloads, periodically execute `PRAGMA wal_checkpoint(TRUNCATE);` during maintenance windows to maintain compact WAL file sizes.
4. **PostgreSQL Migration Path:** The models (`TenantApiKey`, `DurableEvidenceRecord`) use standard SQLAlchemy constructs compatible with PostgreSQL. When transitioning from SQLite to PostgreSQL, simply change `DATABASE_URL` in `.env` without modifying business logic.
