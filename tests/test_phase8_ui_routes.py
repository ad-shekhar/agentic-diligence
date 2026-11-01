"""
Phase 8 Integration & Route Verification Tests.

Validates the complete multi-page architecture:
- Experience A: Public Product Website routes (/, /product, /capabilities, /how-it-works, /trust, /docs, /get-started)
- Experience B: Authenticated / Managed SaaS Application Workspace shell (/app, /app/projects, /app/settings, etc.)
- Legacy Cockpit Fallback (/cockpit)
- Static design system and client router assets (/static/css/design-system.css, /static/js/app-router.js)
- API endpoint for evaluated company catalog (/api/v1/companies)
- API Documentation endpoint (/api/docs)
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_public_landing_page(client):
    """Verify the root landing page renders with hero and company teaser."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Agentic Diligence" in response.text
    assert "Don't Trust the Claim." in response.text
    assert "Verify the Reality." in response.text
    assert "AcmeAI" in response.text
    assert "EVIDENCE-FIRST RUNTIME DILIGENCE FOR AI AGENTS" in response.text


def test_public_product_page(client):
    """Verify the product tour page renders with architecture and engine descriptions."""
    response = client.get("/product")
    assert response.status_code == 200
    assert "Product Architecture" in response.text
    assert "Multi-Source Evidence Ingestion" in response.text
    assert "Deterministic Diligence Engine" in response.text


def test_public_capabilities_page(client):
    """Verify the capabilities page displays all 10 analytical engines."""
    response = client.get("/capabilities")
    assert response.status_code == 200
    assert "Ten Specialized Diligence Engines" in response.text
    assert "Autonomy & Human Intervention Rate" in response.text
    assert "Telemetry-Attributable Unit Economics" in response.text
    assert "AI Bill of Materials (AIBOM)" in response.text
    assert "CycloneDX" in response.text
    assert "What-If Economic Stress Simulator" in response.text


def test_public_how_it_works_page(client):
    """Verify the how it works page details the 4-stage pipeline."""
    response = client.get("/how-it-works")
    assert response.status_code == 200
    assert "From Raw Telemetry to Verifiable Investment Verdicts" in response.text
    assert "Stage 1: Connect & Ingest Telemetry" in response.text
    assert "Stage 2: Normalize & Segment Tasks" in response.text
    assert "Stage 3: Mathematically Verify Claims" in response.text
    assert "Stage 4: Decide & Compile Evidence Package" in response.text


def test_public_trust_page(client):
    """Verify the trust page renders epistemic levels and dark-zone rules."""
    response = client.get("/trust")
    assert response.status_code == 200
    assert "Engineered for Verifiable Mathematical Trust" in response.text
    assert "The 4-Tier Epistemic Trust Ladder" in response.text
    assert "Dark-Zone Threshold (35% Rule)" in response.text
    assert "Self-Reported Claim" in response.text


def test_public_docs_page(client):
    """Verify docs page includes CLI, REST endpoints, and link to Swagger UI."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "Agentic Diligence Documentation" in response.text
    assert "/v1/traces" in response.text
    assert "/api/docs" in response.text


def test_public_get_started_page(client):
    """Verify get started onboarding wizard displays benchmark presets."""
    response = client.get("/get-started")
    assert response.status_code == 200
    assert "Start an Agent Diligence Audit" in response.text
    assert "Preset Benchmark Scenario" in response.text
    assert "AcmeAI" in response.text


def test_legacy_cockpit_fallback(client):
    """Verify legacy single-page cockpit remains accessible at /cockpit."""
    response = client.get("/cockpit")
    assert response.status_code == 200
    assert "Agentic Diligence" in response.text


def test_saas_app_workspace_routes(client):
    """Verify SaaS application shell renders for /app and subroutes."""
    routes_to_test = [
        "/app",
        "/app/projects",
        "/app/projects/new",
        "/app/projects/acme-ai/claims",
        "/app/projects/acme-ai/autonomy",
        "/app/projects/acme-ai/economics",
        "/app/projects/acme-ai/aibom",
        "/app/integrations",
        "/app/settings",
    ]
    for route in routes_to_test:
        response = client.get(route)
        assert response.status_code == 200, f"Route {route} failed with {response.status_code}"
        assert "Agentic Diligence" in response.text
        assert "app-router.js" in response.text
        assert "app-sidebar" in response.text


def test_static_assets_delivery(client):
    """Verify CSS design system and JS router are served correctly."""
    css_res = client.get("/static/css/design-system.css")
    assert css_res.status_code == 200
    assert "--bg-root" in css_res.text
    assert "--accent-primary" in css_res.text

    js_res = client.get("/static/js/app-router.js")
    assert js_res.status_code == 200
    assert "handleRoute" in js_res.text
    assert "loadCompaniesList" in js_res.text


def test_api_companies_endpoint(client):
    """Verify the companies catalog API endpoint returns a list."""
    response = client.get("/api/v1/companies")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_api_docs_endpoint(client):
    """Verify Swagger UI is accessible at /api/docs."""
    response = client.get("/api/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower() or "openapi" in response.text.lower()
