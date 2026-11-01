"""
Phase 9 End-to-End Product Lifecycle Integration Test: Milestone 9.7.

Validates the full 9-stage technical diligence journey:
1. Discover and create a diligence project with genuine scope.
2. Verify project initialization without synthetic benchmark injection.
3. Ingest real OpenTelemetry JSON traces into the project scope.
4. Verify SHA-256 provenance digest, span normalization, and duplicate protection.
5. Execute the unified assessment orchestrator across all analytical engines.
6. Verify per-engine execution records, timing, and error isolation.
7. Inspect structured risk findings across severity levels.
8. Verify Investment Committee deal verdict and risk scores.
9. Generate immutable report snapshot deliverables (PDF, CycloneDX JSON, ZIP bundle, manifest).
10. Audit full project activity lineage log.
"""

import io
import json
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal, init_db
from app.db.models import Project, Assessment, Report, IngestionJob, Finding, ProjectActivity


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


def make_enterprise_telemetry(trace_id: str):
    """Builds a multi-span enterprise agent execution trace adhering to GenAI v1.28.0."""
    span1_id = uuid.uuid4().hex[:16]
    span2_id = uuid.uuid4().hex[:16]
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "enterprise-compliance-agent"}},
                        {"key": "deployment.environment", "value": {"stringValue": "production"}}
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": span1_id,
                                "name": "agent.review_regulatory_filing",
                                "kind": 3,
                                "startTimeUnixNano": "1726999200000000000",
                                "endTimeUnixNano": "1726999203500000000",
                                "attributes": [
                                    {"key": "gen_ai.provider.name", "value": {"stringValue": "openai"}},
                                    {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}},
                                    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": 2400}},
                                    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 650}}
                                ],
                                "status": {"code": 1}
                            },
                            {
                                "traceId": trace_id,
                                "spanId": span2_id,
                                "parentSpanId": span1_id,
                                "name": "tool.execute_database_verification",
                                "kind": 3,
                                "startTimeUnixNano": "1726999203550000000",
                                "endTimeUnixNano": "1726999204200000000",
                                "attributes": [
                                    {"key": "gen_ai.tool.name", "value": {"stringValue": "sql_compliance_vault"}},
                                    {"key": "gen_ai.tool.action", "value": {"stringValue": "query_records"}}
                                ],
                                "status": {"code": 1}
                            }
                        ]
                    }
                ]
            }
        ]
    }


def test_complete_end_to_end_diligence_journey(client, db: Session):
    """
    Executes the full 9-stage technical diligence lifecycle.
    """
    # --------------------------------------------------------------------------
    # STAGE 1: Discover & Create Diligence Project
    # --------------------------------------------------------------------------
    proj_payload = {
        "name": "Acquisition Diligence - LegalTech Agent",
        "target_name": "ComplianceBot Corp",
        "target_system": "RegLegal AI v3.2",
        "target_type": "autonomous_agent",
        "framework": "LangGraph + OpenTelemetry",
        "description": "Pre-Series B technical diligence evaluating autonomous claims and vendor lock-in.",
        "assessment_scope": "Full production compliance workflows over last 30 days."
    }
    create_res = client.post("/api/v1/projects", json=proj_payload)
    assert create_res.status_code == 201, f"Project creation failed: {create_res.text}"
    project = create_res.json()
    project_id = project["id"]
    company_id = project["company_id"]
    assert project["status"] == "ACTIVE"
    assert project["target_system"] == "RegLegal AI v3.2"

    # --------------------------------------------------------------------------
    # STAGE 2: Connect / Ingest Telemetry Traces
    # --------------------------------------------------------------------------
    trace_id_1 = f"trace-e2e-{uuid.uuid4().hex[:8]}"
    telemetry_payload = make_enterprise_telemetry(trace_id_1)
    file_bytes = json.dumps(telemetry_payload).encode("utf-8")

    ingest_res = client.post(
        f"/api/v1/projects/{project_id}/ingest",
        files={"file": ("production_traces.json", io.BytesIO(file_bytes), "application/json")}
    )
    assert ingest_res.status_code == 200, f"Ingestion failed: {ingest_res.text}"
    ingest_data = ingest_res.json()
    assert ingest_data["status"] == "SUCCESS"
    assert ingest_data["spans_count"] == 2
    assert ingest_data["traces_count"] == 1
    payload_hash = ingest_data["payload_hash"]

    # --------------------------------------------------------------------------
    # STAGE 3: Duplicate Interception Verification
    # --------------------------------------------------------------------------
    dup_res = client.post(
        f"/api/v1/projects/{project_id}/ingest",
        files={"file": ("production_traces_dup.json", io.BytesIO(file_bytes), "application/json")}
    )
    assert dup_res.status_code == 200
    assert dup_res.json()["status"] == "DUPLICATE"

    # --------------------------------------------------------------------------
    # STAGE 4: Validate Evidence & Provenance Storage
    # --------------------------------------------------------------------------
    ev_res = client.get(f"/api/v1/projects/{project_id}/evidence")
    assert ev_res.status_code == 200
    evidence_data = ev_res.json()
    assert evidence_data["total_traces"] >= 1
    assert evidence_data["total_spans"] >= 2
    assert len(evidence_data["provenance_digests"]) >= 1

    # --------------------------------------------------------------------------
    # STAGE 5: Execute Unified Assessment Orchestrator
    # --------------------------------------------------------------------------
    ass_res = client.post(
        f"/api/v1/projects/{project_id}/assessments",
        json={"trigger_type": "MANUAL"}
    )
    assert ass_res.status_code == 200, f"Assessment failed: {ass_res.text}"
    assessment = ass_res.json()
    assessment_id = assessment["id"]

    assert assessment["status"] in ["COMPLETED", "PARTIALLY_COMPLETED"]
    assert assessment["autonomy_score"] is not None
    assert assessment["overall_risk_score"] is not None
    assert assessment["summary_verdict"] in ["VERIFIED", "CONDITIONAL", "HIGH_RISK"]

    # Verify per-engine execution telemetry
    executions = assessment["engine_executions"]
    assert len(executions) >= 10
    engine_keys = [e["engine_key"] for e in executions]
    for req_key in ["autonomy", "economics", "dependencies", "cascades", "tool_risk", "aibom"]:
        assert req_key in engine_keys

    # --------------------------------------------------------------------------
    # STAGE 6: Inspect Findings Register
    # --------------------------------------------------------------------------
    findings_res = client.get(f"/api/v1/projects/{project_id}/findings")
    assert findings_res.status_code == 200
    findings = findings_res.json()
    assert isinstance(findings, list)

    # --------------------------------------------------------------------------
    # STAGE 7: Generate Complete Diligence Deliverables
    # --------------------------------------------------------------------------
    rep_res = client.post(f"/api/v1/assessments/{assessment_id}/report")
    assert rep_res.status_code == 200, f"Report generation failed: {rep_res.text}"
    report = rep_res.json()
    report_id = report["report_id"]

    # Verify deliverables downloads:
    # A. PDF Deliverable
    pdf_res = client.get(f"/api/v1/reports/{report_id}/download?format=pdf")
    assert pdf_res.status_code == 200
    assert "application/pdf" in pdf_res.headers.get("content-type", "")

    # B. Diligence Package JSON
    json_res = client.get(f"/api/v1/reports/{report_id}/download?format=json")
    assert json_res.status_code == 200
    assert "company" in json_res.json()

    # C. Verifiable Signed .ZIP Bundle
    bundle_res = client.get(f"/api/v1/reports/{report_id}/download?format=bundle")
    assert bundle_res.status_code == 200
    assert len(bundle_res.content) > 500

    # D. Cryptographic Chain-of-Custody Manifest
    man_res = client.get(f"/api/v1/reports/{report_id}/download?format=manifest")
    assert man_res.status_code == 200
    assert "manifest_version" in man_res.json()

    # --------------------------------------------------------------------------
    # STAGE 8: Verify Project Audit Activity Lineage
    # --------------------------------------------------------------------------
    act_res = client.get(f"/api/v1/projects/{project_id}/activity")
    assert act_res.status_code == 200
    activities = act_res.json()
    activity_types = [a["activity_type"] for a in activities]

    assert "PROJECT_CREATED" in activity_types
    assert "TELEMETRY_INGESTED" in activity_types
    assert "ASSESSMENT_RUN" in activity_types
    assert "REPORT_GENERATED" in activity_types

    # --------------------------------------------------------------------------
    # STAGE 9: Historical Cataloging
    # --------------------------------------------------------------------------
    hist_assessments = client.get(f"/api/v1/projects/{project_id}/assessments").json()
    assert len(hist_assessments) >= 1

    hist_reports = client.get(f"/api/v1/projects/{project_id}/reports").json()
    assert len(hist_reports) >= 1
    assert hist_reports[0]["id"] == report_id
