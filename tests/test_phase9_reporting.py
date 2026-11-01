"""
Phase 9 Integration Tests: Milestone 9.6 Deliverable Reporting Engine.

Validates:
- Snapshot report generation linked to assessment executions
- Board-ready PDF report generation and download
- CycloneDX-compatible JSON package download
- Verifiable signed .zip bundle artifact download
- Cryptographic chain-of-custody manifest download
- Project-level report catalog listing
"""

import os
import io
import json
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal, init_db
from app.db.models import Project, Report, Assessment


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


def make_sample_traces(trace_id: str):
    span_id = uuid.uuid4().hex[:16]
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "report-agent"}}]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": span_id,
                                "name": "agent.generate_contract",
                                "kind": 3,
                                "startTimeUnixNano": "1726999200000000000",
                                "endTimeUnixNano": "1726999201500000000",
                                "attributes": [
                                    {"key": "gen_ai.provider.name", "value": {"stringValue": "anthropic"}},
                                    {"key": "gen_ai.request.model", "value": {"stringValue": "claude-3-5-sonnet"}},
                                    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": 800}},
                                    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 350}}
                                ],
                                "status": {"code": 1}
                            }
                        ]
                    }
                ]
            }
        ]
    }


def test_generate_and_download_report_deliverables(client, db: Session):
    """Verify generating a diligence report produces real downloadable deliverables (PDF, JSON, ZIP bundle, manifest)."""
    # 1. Create project
    proj = client.post("/api/v1/projects", json={
        "name": "Deliverable Reporting Target",
        "target_name": "ReportBot AI",
        "target_system": "ContractWriter Agent"
    }).json()
    proj_id = proj["id"]

    # 2. Ingest telemetry
    tid = f"trace-report-{uuid.uuid4().hex[:8]}"
    client.post(f"/api/v1/projects/{proj_id}/ingest", json=make_sample_traces(tid))

    # 3. Run assessment
    ass_res = client.post(f"/api/v1/projects/{proj_id}/assessments")
    assert ass_res.status_code == 200
    ass_id = ass_res.json()["id"]

    # 4. Generate report snapshot linked to assessment
    rep_res = client.post(f"/api/v1/assessments/{ass_id}/report")
    assert rep_res.status_code == 200
    rep_data = rep_res.json()

    assert rep_data["report_id"] is not None
    assert rep_data["assessment_id"] == ass_id
    assert rep_data["project_id"] == proj_id
    assert "pdf_download_url" in rep_data
    assert "bundle_download_url" in rep_data
    report_id = rep_data["report_id"]

    # 5. Download and verify PDF
    pdf_res = client.get(f"/api/v1/reports/{report_id}/download?format=pdf")
    assert pdf_res.status_code == 200
    assert "application/pdf" in pdf_res.headers.get("content-type", "")
    assert len(pdf_res.content) > 1000

    # 6. Download and verify JSON Package
    json_res = client.get(f"/api/v1/reports/{report_id}/download?format=json")
    assert json_res.status_code == 200
    json_data = json_res.json()
    assert "company" in json_data
    assert "interventions" in json_data
    assert "economics" in json_data

    # 7. Download and verify ZIP Diligence Bundle
    bundle_res = client.get(f"/api/v1/reports/{report_id}/download?format=bundle")
    assert bundle_res.status_code == 200
    assert "application/zip" in bundle_res.headers.get("content-type", "") or "zip" in bundle_res.headers.get("content-type", "")
    assert len(bundle_res.content) > 500

    # 8. Download and verify Manifest
    man_res = client.get(f"/api/v1/reports/{report_id}/download?format=manifest")
    assert man_res.status_code == 200
    man_data = man_res.json()
    assert "manifest_version" in man_data
    assert "company" in man_data
    assert man_data["company"]["id"] is not None

    # 9. Verify project reports catalog list
    list_res = client.get(f"/api/v1/projects/{proj_id}/reports")
    assert list_res.status_code == 200
    reports_list = list_res.json()
    assert len(reports_list) >= 1
    assert reports_list[0]["id"] == report_id
    assert reports_list[0]["has_pdf"] is True
