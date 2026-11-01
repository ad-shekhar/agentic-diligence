"""
Phase 9 Integration Tests: Milestone 9.2 Complete Onboarding.

Validates:
- Path A: Calibrated Benchmark evaluation execution, ground-truth disclosure, auto-seeded project
- Path B: Custom target evaluation creation with zero synthetic fallback data
- Isolation: Custom target has exactly 0 traces and is ready for real telemetry
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal, init_db
from app.db.models import Project, Company, Trace


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


def test_onboarding_benchmark_path(client, db: Session):
    """Verify Path A executes calibrated benchmark scenario and associates a Project."""
    response = client.get("/api/v1/scenarios/scenario_b/run?sample_size=30")
    assert response.status_code == 200
    data = response.json()
    assert "company" in data
    comp_id = data["company"]["id"]

    # Verify project was auto-seeded for this benchmark company
    from app.projects.service import get_project_by_id_or_company
    proj = get_project_by_id_or_company(db, comp_id)
    assert proj is not None
    assert proj.company_id == comp_id
    assert proj.status == "ACTIVE"


def test_onboarding_custom_target_path(client, db: Session):
    """Verify Path B creates a genuine project without synthetic data injection."""
    payload = {
        "name": "Custom FinTech Assistant Diligence",
        "target_name": "FinTech Corp",
        "target_system": "Automated Reconciliation Bot",
        "target_type": "autonomous_agent",
        "framework": "CrewAI Hierarchical Agent",
        "description": "Evaluating claims of 99% accuracy on financial ledger reconciliations.",
        "assessment_scope": "Ledger update spans"
    }
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201
    proj_data = response.json()
    proj_id = proj_data["id"]
    comp_id = proj_data["company_id"]

    # Verify that company has 0 traces - ZERO mock data injected!
    traces = db.query(Trace).filter(Trace.company_id == comp_id).all()
    assert len(traces) == 0, "Custom onboarding must not inject benchmark traces!"

    # Verify retrieval from package route returns empty coverage
    pkg_res = client.get(f"/api/v1/companies/{comp_id}/package")
    assert pkg_res.status_code == 200
    pkg = pkg_res.json()
    assert pkg["company"]["id"] == comp_id
    assert pkg["interventions"]["total_traces"] == 0
    assert pkg["economics"]["total_tasks"] == 0
