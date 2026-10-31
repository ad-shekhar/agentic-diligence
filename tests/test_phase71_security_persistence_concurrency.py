"""
Phase 7.1 Integration Tests: Security, Persistence & Concurrency Foundation.

Validates the three P0 architectural remediation milestones:
- Milestone A: API key authentication, tenant authorization, scope boundaries, cross-tenant isolation.
- Milestone B: Durable relational SQLite persistence, cold-start registry hydration, persistent duplicate detection across process restarts.
- Milestone C: Concurrency thread-safety, RLock synchronization, multi-threaded ingestion under SQLite WAL.
"""

import concurrent.futures
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters.base import AdapterCapability, ProvenanceEnvelope
from app.adapters.pipeline import UnifiedVerificationPipeline
from app.adapters.registry import (
    EvidenceRecord,
    EvidenceStatus,
    SourceType,
    UnifiedEvidenceRegistry,
)
from app.db.models import (
    Company,
    DurableEvidenceRecord,
    PayloadProvenance,
    Tenant,
    TenantApiKey,
)
from app.db.session import Base, SessionLocal, get_db, init_db
from app.epistemic.claims import ClaimDimension, ClaimSchema, ComparisonOperator
from app.epistemic.tags import EpistemicTag, TrustLevel, VerificationVerdict
from app.ingestion.schema import NormalizedSpan
from app.main import app
from app.security.auth import (
    AuthenticatedContext,
    create_test_api_key,
    generate_api_key,
    hash_api_key,
)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensures database schema and WAL mode are initialized."""
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def test_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def make_otlp_payload(trace_id: str, span_id: str, duration_ms: float = 100.0) -> dict:
    start_ns = 1729000000000000000
    end_ns = start_ns + int(duration_ms * 1_000_000)
    return {
        "spans": [
            {
                "trace_id": trace_id,
                "span_id": span_id,
                "name": "ai_agent_step",
                "start_time_ns": start_ns,
                "end_time_ns": end_ns,
                "attributes": {
                    "gen_ai.provider.name": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.usage.input_tokens": 120,
                    "gen_ai.usage.output_tokens": 60,
                },
            }
        ]
    }


# ==============================================================================
# Milestone A: Authentication & Tenant Authorization Tests
# ==============================================================================

class TestMilestoneASecurity:
    """Validates API authentication, tenant isolation, and scope boundaries."""

    def test_missing_credentials_rejected_401(self, client):
        """Requests without API key credentials return 401 Unauthorized."""
        res_ingest = client.post("/api/v1/evidence/ingest", json={"spans": []})
        assert res_ingest.status_code == 401
        assert "credentials missing" in res_ingest.json()["detail"].lower()

        res_verify = client.post("/api/v1/evidence/verify", json={"claims": []})
        assert res_verify.status_code == 401

        res_records = client.get("/api/v1/evidence/records")
        assert res_records.status_code == 401

        res_prov = client.get("/api/v1/evidence/provenance")
        assert res_prov.status_code == 401

    def test_invalid_and_revoked_key_rejected_401(self, client, test_db):
        """Requests with forged or deactivated keys return 401 Unauthorized."""
        # 1. Non-existent random key
        bad_headers = {"X-API-Key": "agd_live_000000000000000000000000000000000000000000000000"}
        res = client.get("/api/v1/evidence/records?company_id=comp-any", headers=bad_headers)
        assert res.status_code == 401
        assert "invalid or revoked" in res.json()["detail"].lower()

        # 2. Deactivated (revoked) key
        raw_key, key_rec = create_test_api_key(test_db, company_id=f"comp-revoked-{uuid.uuid4().hex[:6]}")
        key_rec.is_active = False
        test_db.commit()

        res_revoked = client.get("/api/v1/evidence/records?company_id=comp-any", headers={"X-API-Key": raw_key})
        assert res_revoked.status_code == 401
        assert "invalid or revoked" in res_revoked.json()["detail"].lower()

    def test_expired_key_rejected_401(self, client, test_db):
        """Requests with past expires_at return 401 Unauthorized."""
        cid = f"comp-expired-{uuid.uuid4().hex[:6]}"
        raw_key, key_rec = create_test_api_key(test_db, company_id=cid)
        key_rec.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        test_db.commit()

        res = client.get(f"/api/v1/evidence/records?company_id={cid}", headers={"X-API-Key": raw_key})
        assert res.status_code == 401
        assert "expired" in res.json()["detail"].lower()

    def test_bearer_authorization_header_accepted(self, client, test_db):
        """Authorization: Bearer <key> is supported interchangeably with X-API-Key."""
        cid = f"comp-bearer-{uuid.uuid4().hex[:6]}"
        raw_key, _ = create_test_api_key(test_db, company_id=cid)

        headers = {"Authorization": f"Bearer {raw_key}"}
        res = client.get(f"/api/v1/evidence/records?company_id={cid}", headers=headers)
        assert res.status_code == 200

    def test_cross_tenant_access_prevented_403(self, client, test_db):
        """A tenant cannot access or poison another tenant's company evidence."""
        cid_a = f"company-a-{uuid.uuid4().hex[:6]}"
        cid_b = f"company-b-{uuid.uuid4().hex[:6]}"

        raw_key_a, _ = create_test_api_key(test_db, company_id=cid_a, tenant_id="tenant-alpha")
        raw_key_b, _ = create_test_api_key(test_db, company_id=cid_b, tenant_id="tenant-beta")

        headers_a = {"X-API-Key": raw_key_a}

        # Tenant A tries to ingest into Tenant B's company
        payload = make_otlp_payload("trace-poison-01", "span-poison-01")
        res_poison = client.post(
            f"/api/v1/evidence/ingest?company_id={cid_b}&source_type=otlp",
            json=payload,
            headers=headers_a,
        )
        assert res_poison.status_code == 403
        assert "forbidden" in res_poison.json()["detail"].lower()

        # Tenant A tries to read Tenant B's evidence records
        res_snoop = client.get(f"/api/v1/evidence/records?company_id={cid_b}", headers=headers_a)
        assert res_snoop.status_code == 403

        # Tenant A tries to read Tenant B's provenance envelopes
        res_prov = client.get(f"/api/v1/evidence/provenance?company_id={cid_b}", headers=headers_a)
        assert res_prov.status_code == 403

        # Tenant A tries to verify claims against Tenant B's company
        res_verify = client.post(
            "/api/v1/evidence/verify",
            json={"company_id": cid_b, "claims": []},
            headers=headers_a,
        )
        assert res_verify.status_code == 403

    def test_scope_enforcement_read_vs_write(self, client, test_db):
        """Read-only keys cannot write; write-only keys cannot read."""
        cid = f"comp-scopes-{uuid.uuid4().hex[:6]}"
        read_key, _ = create_test_api_key(test_db, company_id=cid, scopes="evidence:read")
        write_key, _ = create_test_api_key(test_db, company_id=cid, scopes="evidence:write")

        # Read-only key attempts ingestion -> 403
        payload = make_otlp_payload("trace-rw-01", "span-rw-01")
        res_write_denied = client.post(
            f"/api/v1/evidence/ingest?company_id={cid}&source_type=otlp",
            json=payload,
            headers={"X-API-Key": read_key},
        )
        assert res_write_denied.status_code == 403
        assert "evidence:write" in res_write_denied.json()["detail"]

        # Write-only key successfully ingests
        res_write_ok = client.post(
            f"/api/v1/evidence/ingest?company_id={cid}&source_type=otlp",
            json=payload,
            headers={"X-API-Key": write_key},
        )
        assert res_write_ok.status_code == 200

        # Write-only key attempts read -> 403
        res_read_denied = client.get(
            f"/api/v1/evidence/records?company_id={cid}",
            headers={"X-API-Key": write_key},
        )
        assert res_read_denied.status_code == 403
        assert "evidence:read" in res_read_denied.json()["detail"]


# ==============================================================================
# Milestone B: Durable Relational Persistence Across Process Restarts
# ==============================================================================

class TestMilestoneBPersistence:
    """Validates durability across restarts, schema fidelity, and persistent duplicate tracking."""

    def test_persistence_and_cold_start_hydration(self, test_db):
        """Evidence ingested in registry A survives process restart and hydrates in cold registry B."""
        company_id = f"comp-persist-{uuid.uuid4().hex[:6]}"

        # Registry A: Ingests 5 traces with database session
        reg_a = UnifiedEvidenceRegistry()
        reg_a.clear()

        for i in range(5):
            raw = json.dumps(make_otlp_payload(f"trace-dur-{i}", f"span-dur-{i}")).encode("utf-8")
            receipt = reg_a.register_payload(
                raw_bytes=raw,
                source_type=SourceType.OTLP,
                company_id=company_id,
                db=test_db,
            )
            assert receipt.status == "SUCCESS"

        # Verify rows were committed to SQLite table durable_evidence_records
        db_rows = test_db.query(DurableEvidenceRecord).filter_by(company_id=company_id).all()
        assert len(db_rows) == 5

        # SIMULATE PROCESS RESTART: Create a brand new registry instance with zero in-memory cache
        reg_b = UnifiedEvidenceRegistry()
        # Verify in-memory cache is cold
        assert len(reg_b._records_by_id) == 0

        # Query records through reg_b with db session passed
        records = reg_b.get_records(company_id=company_id, db=test_db)
        assert len(records) == 5
        assert reg_b._records_by_id  # Cache was populated

        # Check full fidelity of hydrated NormalizedSpan
        rec0 = records[0]
        assert isinstance(rec0.span, NormalizedSpan)
        assert rec0.span.provider_name == "openai"
        assert rec0.span.requested_model == "gpt-4o"
        assert rec0.span.input_tokens == 120
        assert rec0.span.output_tokens == 60
        assert rec0.trust_level == TrustLevel.T1
        assert rec0.epistemic_tag == EpistemicTag.OBSERVED

        # Check provenance envelope hydration
        envelopes = reg_b.get_provenance_envelopes(company_id=company_id, db=test_db)
        assert len(envelopes) >= 1
        assert isinstance(envelopes[0], ProvenanceEnvelope)
        assert len(envelopes[0].payload_sha256) == 64

    def test_persistent_duplicate_detection_across_restart(self, test_db):
        """Duplicate detection operates correctly even after an in-memory cache wipe."""
        company_id = f"comp-dup-restart-{uuid.uuid4().hex[:6]}"
        raw = json.dumps(make_otlp_payload("trace-dup-fix", "span-dup-fix")).encode("utf-8")

        # Initial ingestion on Registry 1
        reg1 = UnifiedEvidenceRegistry()
        reg1.clear()
        rcpt1 = reg1.register_payload(raw, source_type=SourceType.OTLP, company_id=company_id, db=test_db)
        assert rcpt1.duplicates_detected == 0

        # Simulate complete restart / new process with completely fresh registry
        reg2 = UnifiedEvidenceRegistry()
        assert len(reg2._seen_spans) == 0

        # Re-ingest the exact same trace into Registry 2
        rcpt2 = reg2.register_payload(raw, source_type=SourceType.OTLP, company_id=company_id, db=test_db)
        assert rcpt2.duplicates_detected == 1

        # Query records with include_duplicates=True
        all_recs = reg2.get_records(company_id=company_id, include_duplicates=True, db=test_db)
        assert len(all_recs) == 2
        valid_recs = [r for r in all_recs if r.status == EvidenceStatus.VALID]
        dup_recs = [r for r in all_recs if r.status == EvidenceStatus.DUPLICATE]
        assert len(valid_recs) == 1
        assert len(dup_recs) == 1

    def test_verification_pipeline_cold_start_from_database(self, test_db):
        """A freshly booted pipeline can verify claims using only persisted SQLite records."""
        company_id = f"comp-pipe-cold-{uuid.uuid4().hex[:6]}"

        # Ingest 16 autonomous traces via pipeline A
        pipeline_a = UnifiedVerificationPipeline()
        pipeline_a.registry.clear()

        for i in range(16):
            raw = json.dumps(make_otlp_payload(f"trace-e2e-{i:03d}", f"span-e2e-{i}")).encode("utf-8")
            pipeline_a.ingest_evidence(raw, source_type=SourceType.OTLP, company_id=company_id, db=test_db)

        # Boot completely fresh pipeline B
        fresh_registry = UnifiedEvidenceRegistry()
        pipeline_b = UnifiedVerificationPipeline(registry=fresh_registry)

        claim = ClaimSchema(
            claim_id="cold-start-autonomy-claim",
            dimension=ClaimDimension.AUTONOMY,
            stated_claim_text="System autonomy is at least 80%",
            target_operator=ComparisonOperator.GREATER_EQUAL,
            target_value=80.0,
            unit="%",
        )

        # Verify claims on fresh pipeline B pointing to db
        res = pipeline_b.verify_claims([claim], company_id=company_id, min_sample_size=15, db=test_db)
        assert res.total_evidence_records >= 16
        assert len(res.matrix.entries) == 1
        assert res.matrix.entries[0].verification_verdict == VerificationVerdict.VERIFIED


# ==============================================================================
# Milestone C: Concurrency Safety & Multi-Threading Tests
# ==============================================================================

class TestMilestoneCConcurrency:
    """Validates thread synchronization, RLock protection, and concurrent SQLite WAL writes."""

    def test_multithreaded_registry_ingestion_thread_safety(self, test_db):
        """10 threads concurrently registering distinct payloads into the same registry."""
        registry = UnifiedEvidenceRegistry()
        registry.clear()
        company_id = f"comp-concurrent-{uuid.uuid4().hex[:6]}"

        threads_count = 10
        traces_per_thread = 5
        errors = []

        def worker(thread_idx: int):
            db = SessionLocal()
            try:
                for j in range(traces_per_thread):
                    tid = f"th-{thread_idx:02d}-tr-{j:02d}"
                    sid = f"th-{thread_idx:02d}-sp-{j:02d}"
                    payload = json.dumps(make_otlp_payload(tid, sid)).encode("utf-8")
                    receipt = registry.register_payload(
                        raw_bytes=payload,
                        source_type=SourceType.OTLP,
                        company_id=company_id,
                        db=db,
                    )
                    assert receipt.status == "SUCCESS"
            except Exception as ex:
                errors.append(ex)
            finally:
                db.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=threads_count) as executor:
            futures = [executor.submit(worker, i) for i in range(threads_count)]
            concurrent.futures.wait(futures)

        assert not errors, f"Concurrent workers encountered errors: {errors}"

        # Total spans ingested should equal threads_count * traces_per_thread = 50
        records = registry.get_records(company_id=company_id, db=test_db)
        assert len(records) == threads_count * traces_per_thread

    def test_concurrent_read_write_interleaving(self, test_db):
        """Concurrent reader threads read consistent states while writers are ingesting."""
        registry = UnifiedEvidenceRegistry()
        registry.clear()
        company_id = f"comp-rw-interleave-{uuid.uuid4().hex[:6]}"

        stop_event = threading.Event()
        read_errors = []
        read_counts = []

        def reader():
            db = SessionLocal()
            try:
                while not stop_event.is_set():
                    recs = registry.get_records(company_id=company_id, db=db)
                    read_counts.append(len(recs))
            except Exception as e:
                read_errors.append(e)
            finally:
                db.close()

        def writer():
            db = SessionLocal()
            try:
                for i in range(15):
                    raw = json.dumps(make_otlp_payload(f"rw-trace-{i}", f"rw-span-{i}")).encode("utf-8")
                    registry.register_payload(raw, source_type=SourceType.OTLP, company_id=company_id, db=db)
            finally:
                db.close()

        reader_thread = threading.Thread(target=reader)
        writer_thread = threading.Thread(target=writer)

        reader_thread.start()
        writer_thread.start()

        writer_thread.join()
        stop_event.set()
        reader_thread.join()

        assert not read_errors, f"Reader thread failed: {read_errors}"
        assert len(read_counts) > 0
        final_recs = registry.get_records(company_id=company_id, db=test_db)
        assert len(final_recs) == 15
