"""
Phase 9 Integration Tests: Milestone 9.3 Telemetry and Evidence Ingestion.

Validates:
- End-to-end file upload and server-side JSON parsing
- Pre-parsing SHA-256 fingerprinting
- Duplicate payload detection without re-insertion
- IngestionJob history and error recording on malformed payloads
- Project-level evidence summary and provenance records
"""

import io
import json
import hashlib
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal, init_db
from app.db.models import Project, IngestionJob, PayloadProvenance, Trace


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def make_sample_otlp_payload(trace_id="4bf92f3577b34da6a3ce929d0e0e4736", span_id=None):
    effective_span_id = span_id or hashlib.sha256(trace_id.encode("utf-8")).hexdigest()[:16]
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "support-agent"}}]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": effective_span_id,
                                "name": "agent.resolve_ticket",
                                "kind": 3,
                                "startTimeUnixNano": "1726999200000000000",
                                "endTimeUnixNano": "1726999201500000000",
                                "attributes": [
                                    {"key": "gen_ai.provider.name", "value": {"stringValue": "openai"}},
                                    {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}},
                                    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": 450}},
                                    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 120}}
                                ],
                                "status": {"code": 1}
                            }
                        ]
                    }
                ]
            }
        ]
    }


def test_ingest_json_file_success(client, db: Session):
    """Verify uploading a valid OTLP JSON file associates spans and creates an IngestionJob."""
    # Create project
    proj = client.post("/api/v1/projects", json={
        "name": "Live Support Agent Ingestion",
        "target_name": "SupportBot Inc"
    }).json()
    proj_id = proj["id"]

    tid = f"trace-proj-ingest-{uuid.uuid4().hex[:8]}"
    sample_data = make_sample_otlp_payload(tid)
    file_bytes = json.dumps(sample_data).encode("utf-8")

    response = client.post(
        f"/api/v1/projects/{proj_id}/ingest",
        files={"file": ("traces.json", io.BytesIO(file_bytes), "application/json")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["spans_count"] == 1
    assert "payload_hash" in data

    # Verify IngestionJob in DB
    job = db.query(IngestionJob).filter(IngestionJob.id == data["job_id"]).first()
    assert job is not None
    assert job.status == "SUCCESS"
    assert job.filename == "traces.json"


def test_duplicate_payload_detection(client, db: Session):
    """Verify duplicate uploads are safely intercepted without data re-insertion."""
    proj = client.post("/api/v1/projects", json={
        "name": "Dedup Test Project",
        "target_name": "Dedup AI"
    }).json()
    proj_id = proj["id"]

    tid = f"trace-dedup-{uuid.uuid4().hex[:8]}"
    sample_data = make_sample_otlp_payload(tid)
    file_bytes = json.dumps(sample_data).encode("utf-8")

    # Ingest 1st time
    res1 = client.post(
        f"/api/v1/projects/{proj_id}/ingest",
        files={"file": ("batch.json", io.BytesIO(file_bytes), "application/json")}
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "SUCCESS"

    # Ingest 2nd time (duplicate)
    res2 = client.post(
        f"/api/v1/projects/{proj_id}/ingest",
        files={"file": ("batch.json", io.BytesIO(file_bytes), "application/json")}
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "DUPLICATE"
    assert data2["payload_hash"] == res1.json()["payload_hash"]

    # Verify jobs list shows both
    jobs_res = client.get(f"/api/v1/projects/{proj_id}/ingestion-jobs")
    assert jobs_res.status_code == 200
    jobs = jobs_res.json()
    assert len(jobs) == 2
    assert jobs[0]["status"] == "DUPLICATE"
    assert jobs[1]["status"] == "SUCCESS"


def test_ingest_malformed_json(client, db: Session):
    """Verify uploading corrupt JSON fails with 400 and logs FAILED job."""
    proj = client.post("/api/v1/projects", json={
        "name": "Corrupt Upload Test",
        "target_name": "Error Target"
    }).json()
    proj_id = proj["id"]

    bad_bytes = b'{"resourceSpans": [invalid_json_stream...'
    res = client.post(
        f"/api/v1/projects/{proj_id}/ingest",
        files={"file": ("broken.json", io.BytesIO(bad_bytes), "application/json")}
    )
    assert res.status_code == 400
    assert "malformed" in res.text.lower() or "json" in res.text.lower()

    # Verify failed job logged
    jobs = client.get(f"/api/v1/projects/{proj_id}/ingestion-jobs").json()
    assert len(jobs) == 1
    assert jobs[0]["status"] == "FAILED"
    assert jobs[0]["error_message"] is not None


def test_list_project_evidence(client, db: Session):
    """Verify project evidence summary accurately reflects ingested traces and digests."""
    proj = client.post("/api/v1/projects", json={
        "name": "Evidence Summary Target",
        "target_name": "Evidence AI"
    }).json()
    proj_id = proj["id"]

    # Ingest a sample payload
    tid = f"trace-evidence-{uuid.uuid4().hex[:8]}"
    payload = make_sample_otlp_payload(tid)
    post_res = client.post(
        f"/api/v1/projects/{proj_id}/ingest",
        json=payload
    )
    assert post_res.status_code == 200, f"Ingest failed: {post_res.status_code} {post_res.text}"

    ev_res = client.get(f"/api/v1/projects/{proj_id}/evidence")
    assert ev_res.status_code == 200
    ev_data = ev_res.json()
    assert ev_data["total_traces"] >= 1
    assert ev_data["total_spans"] >= 1
    assert len(ev_data["provenance_digests"]) >= 1
