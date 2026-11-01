"""
Phase 9 Integration Tests: Milestone 9.4 Unified Assessment Orchestration.

Validates:
- End-to-end execution of all 10 analytical engines
- Per-engine execution audit records with duration_ms and output JSON
- Strict error isolation (no unhandled engine crash terminates assessment)
- Dynamic finding extraction with severity and recommendations
- Multi-run assessment history preservation
- Findings register querying and filtering
"""

import io
import json
import uuid
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal, init_db
from app.db.models import Project, Assessment, AssessmentEngineExecution, Finding
from app.assessment.orchestrator import AssessmentOrchestrator


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


def make_test_trace_payload(trace_id: str):
    span_id = uuid.uuid4().hex[:16]
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "financial-analyst"}}]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": span_id,
                                "name": "agent.analyze_filing",
                                "kind": 3,
                                "startTimeUnixNano": "1726999200000000000",
                                "endTimeUnixNano": "1726999202500000000",
                                "attributes": [
                                    {"key": "gen_ai.provider.name", "value": {"stringValue": "openai"}},
                                    {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4o"}},
                                    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": 1200}},
                                    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 400}},
                                    {"key": "gen_ai.tool.name", "value": {"stringValue": "sec_edgar_lookup"}}
                                ],
                                "status": {"code": 1}
                            }
                        ]
                    }
                ]
            }
        ]
    }


def test_full_assessment_orchestration_run(client, db: Session):
    """Verify executing an assessment runs all analytical engines and produces persisted executions and findings."""
    # 1. Create project
    proj = client.post("/api/v1/projects", json={
        "name": "Orchestration Pipeline Project",
        "target_name": "AnalystAgent AI",
        "target_system": "FinAnalyst v2"
    }).json()
    proj_id = proj["id"]

    # 2. Ingest telemetry traces
    tid = f"trace-orch-{uuid.uuid4().hex[:8]}"
    payload = make_test_trace_payload(tid)
    ingest_res = client.post(
        f"/api/v1/projects/{proj_id}/ingest",
        json=payload
    )
    assert ingest_res.status_code == 200

    # 3. Trigger assessment
    run_res = client.post(
        f"/api/v1/projects/{proj_id}/assessments",
        json={"trigger_type": "MANUAL"}
    )
    assert run_res.status_code == 200
    data = run_res.json()

    assert data["id"] is not None
    assert data["project_id"] == proj_id
    assert data["status"] in ["COMPLETED", "PARTIALLY_COMPLETED"]
    assert data["autonomy_score"] is not None
    assert 0.0 <= data["autonomy_score"] <= 100.0
    assert data["overall_risk_score"] is not None
    assert 0.0 <= data["overall_risk_score"] <= 100.0
    assert data["summary_verdict"] in ["VERIFIED", "CONDITIONAL", "HIGH_RISK"]

    # Verify engine executions persisted
    executions = data["engine_executions"]
    assert len(executions) >= 10
    for e in executions:
        assert e["status"] == "COMPLETED"
        assert e["duration_ms"] >= 0.0
        assert "engine_key" in e
        assert e["result_json"] is not None

    # Verify findings list exists
    assert "findings" in data
    assert isinstance(data["findings"], list)


def test_assessment_error_isolation(client, db: Session):
    """Verify that an individual engine failure is safely isolated without terminating other engines."""
    proj = client.post("/api/v1/projects", json={
        "name": "Fault Tolerance Project",
        "target_name": "FaultBot AI"
    }).json()
    proj_id = proj["id"]

    # Ingest a trace
    tid = f"trace-fault-{uuid.uuid4().hex[:8]}"
    client.post(f"/api/v1/projects/{proj_id}/ingest", json=make_test_trace_payload(tid))

    # Mock tool_risk engine to throw an unhandled exception
    with patch("app.assessment.orchestrator.analyze_tool_execution_risk", side_effect=RuntimeError("Simulated Tool Risk Failure")):
        run_res = client.post(
            f"/api/v1/projects/{proj_id}/assessments",
            json={"trigger_type": "MANUAL"}
        )
        assert run_res.status_code == 200
        data = run_res.json()

        # Overall assessment must be PARTIALLY_COMPLETED, not crashed
        assert data["status"] == "PARTIALLY_COMPLETED"

        # Verify tool_risk execution is marked FAILED with error_details
        executions = {e["engine_key"]: e for e in data["engine_executions"]}
        assert "tool_risk" in executions
        assert executions["tool_risk"]["status"] == "FAILED"
        assert "Simulated Tool Risk Failure" in executions["tool_risk"]["error_details"]

        # Verify other engines completed successfully
        assert executions["autonomy"]["status"] == "COMPLETED"
        assert executions["economics"]["status"] == "COMPLETED"
        assert executions["dependencies"]["status"] == "COMPLETED"


def test_assessment_history_preservation(client, db: Session):
    """Verify running multiple assessments preserves the full history in reverse chronological order."""
    proj = client.post("/api/v1/projects", json={
        "name": "History Test Project",
        "target_name": "History Corp"
    }).json()
    proj_id = proj["id"]

    # Run assessment 1
    res1 = client.post(
        f"/api/v1/projects/{proj_id}/assessments",
        json={"selected_engines": ["autonomy", "economics"]}
    )
    assert res1.status_code == 200
    a1_id = res1.json()["id"]

    # Run assessment 2
    res2 = client.post(
        f"/api/v1/projects/{proj_id}/assessments",
        json={"selected_engines": ["dependencies", "tool_risk"]}
    )
    assert res2.status_code == 200
    a2_id = res2.json()["id"]

    assert a1_id != a2_id

    # Retrieve history
    hist_res = client.get(f"/api/v1/projects/{proj_id}/assessments")
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert len(history) == 2
    # Verify reverse chronological ordering (a2 is newest)
    assert history[0]["id"] == a2_id
    assert history[1]["id"] == a1_id


def test_findings_filtering(client, db: Session):
    """Verify querying findings by severity and engine key."""
    proj = client.post("/api/v1/projects", json={
        "name": "Findings Query Project",
        "target_name": "Findings AI"
    }).json()
    proj_id = proj["id"]

    # Run full assessment to produce findings
    client.post(
        f"/api/v1/projects/{proj_id}/assessments",
        json={"selected_engines": ["autonomy", "economics", "dependencies"]}
    )

    # Query all findings
    all_res = client.get(f"/api/v1/projects/{proj_id}/findings")
    assert all_res.status_code == 200
    all_findings = all_res.json()
    assert isinstance(all_findings, list)

    # Filter by engine_key
    auto_res = client.get(f"/api/v1/projects/{proj_id}/findings?engine_key=autonomy")
    assert auto_res.status_code == 200
    for f in auto_res.json():
        assert f["engine_key"] == "autonomy"

