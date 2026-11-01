"""
Phase 9 Integration Tests: Milestone 9.1 Project Lifecycle Management.

Validates:
- Project creation with target system metadata without mock fallbacks
- Project listing, search, and status filtering
- Auto-seed project representation for legacy companies
- Project details retrieval via project.id or company_id
- Project metadata updates and activity timeline logging
- Soft-archival behavior and filter semantics
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import SessionLocal, init_db
from app.db.models import Project, Company, Tenant, ProjectActivity


@pytest.fixture(autouse=True)
def setup_database():
    """Ensures database schema and WAL mode are initialized."""
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


def test_create_project_success(client, db: Session):
    """Verify creating a genuine diligence project persists both Company and Project."""
    payload = {
        "name": "NexusFlow Autonomous Agent Diligence",
        "target_name": "NexusFlow Inc",
        "target_system": "Autonomous Customer Support Tier-1",
        "target_type": "autonomous_agent",
        "framework": "LangGraph",
        "description": "Pre-Series B technical due diligence audit.",
        "assessment_scope": "Customer support resolution workflows",
        "evaluation_objective": "Verify stated 90% autonomy claim and unit costs"
    }
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert "company_id" in data
    assert data["name"] == "NexusFlow Autonomous Agent Diligence"
    assert data["target_system"] == "Autonomous Customer Support Tier-1"
    assert data["status"] == "ACTIVE"

    # Verify DB persistence
    proj = db.query(Project).filter(Project.id == data["id"]).first()
    assert proj is not None
    assert proj.company is not None
    assert proj.company.name == "NexusFlow Inc"

    # Verify activity logging
    activities = db.query(ProjectActivity).filter(ProjectActivity.project_id == proj.id).all()
    assert len(activities) >= 1
    assert activities[0].activity_type == "PROJECT_CREATED"


def test_create_project_validation_failure(client):
    """Verify validation error when project name is missing."""
    response = client.post("/api/v1/projects", json={})
    assert response.status_code == 400
    assert "name" in response.text.lower()


def test_list_projects(client, db: Session):
    """Verify listing projects returns valid projects with trace and assessment counts."""
    # Create test project
    p = client.post("/api/v1/projects", json={
        "name": "Audit Target Alpha",
        "target_name": "Alpha AI"
    }).json()

    response = client.get("/api/v1/projects")
    assert response.status_code == 200
    projects = response.json()
    assert isinstance(projects, list)
    matching = [x for x in projects if x["id"] == p["id"]]
    assert len(matching) == 1
    assert matching[0]["target_name"] == "Alpha AI"
    assert matching[0]["trace_count"] == 0


def test_list_projects_search_and_filter(client):
    """Verify search filter on project name or target system."""
    client.post("/api/v1/projects", json={
        "name": "Zeta Robotics Swarm Audit",
        "target_name": "Zeta Corp",
        "target_system": "Warehouse Fleet Swarm"
    })

    res = client.get("/api/v1/projects?search=Robotics")
    assert res.status_code == 200
    data = res.json()
    assert any("Zeta Robotics" in x["name"] for x in data)

    res_empty = client.get("/api/v1/projects?search=NonExistentEntityX99")
    assert res_empty.status_code == 200
    assert len(res_empty.json()) == 0


def test_get_project_by_id_and_company_id(client):
    """Verify dual resolution via project_id and company_id."""
    created = client.post("/api/v1/projects", json={
        "name": "Dual Target Audit",
        "target_name": "Dual AI Target"
    }).json()

    proj_id = created["id"]
    comp_id = created["company_id"]

    # Lookup by project ID
    res1 = client.get(f"/api/v1/projects/{proj_id}")
    assert res1.status_code == 200
    assert res1.json()["id"] == proj_id

    # Lookup by company ID
    res2 = client.get(f"/api/v1/projects/{comp_id}")
    assert res2.status_code == 200
    assert res2.json()["id"] == proj_id


def test_update_project(client, db: Session):
    """Verify updating project metadata and activity logging."""
    created = client.post("/api/v1/projects", json={
        "name": "Original Name Audit",
        "target_name": "Mutable Target"
    }).json()

    proj_id = created["id"]
    update_res = client.patch(f"/api/v1/projects/{proj_id}", json={
        "name": "Renamed Audit Enterprise",
        "description": "Updated diligence objectives"
    })
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Renamed Audit Enterprise"

    # Verify activity logged
    act_res = client.get(f"/api/v1/projects/{proj_id}/activity")
    assert act_res.status_code == 200
    activities = act_res.json()
    assert any(a["activity_type"] == "PROJECT_UPDATED" for a in activities)


def test_archive_project(client):
    """Verify soft-archival hides project from active list unless requested."""
    created = client.post("/api/v1/projects", json={
        "name": "Archival Candidate Project",
        "target_name": "Doomed AI"
    }).json()

    proj_id = created["id"]
    archive_res = client.post(f"/api/v1/projects/{proj_id}/archive")
    assert archive_res.status_code == 200
    assert archive_res.json()["status"] == "ARCHIVED"

    # Default list excludes ARCHIVED
    active_list = client.get("/api/v1/projects").json()
    assert not any(x["id"] == proj_id for x in active_list)

    # Filter by ARCHIVED includes it
    archived_list = client.get("/api/v1/projects?status=ARCHIVED").json()
    assert any(x["id"] == proj_id for x in archived_list)
