import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.ingestion.synthetic import generate_synthetic_scenario
from app.analysis.defensibility import analyze_defensibility_and_moat

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_defensibility_analysis_scenario_a(db_session):
    synth = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=80, seed=42)
    company_id = synth["company_id"]
    
    moat = analyze_defensibility_and_moat(db_session, company_id)
    assert "moat_score" in moat
    assert 0.0 <= moat["moat_score"] <= 100.0
    assert moat["moat_classification"] in [
        "COMMODITY_WRAPPER", "LIGHT_SCAFFOLDING", "PROPRIETARY_COMPOUND_SYSTEM", "DEEP_DEFENSIBLE_MOAT"
    ]
    assert moat["scaffolding_complexity_score"] >= 0.0
    assert moat["weight_sovereignty_score"] >= 0.0
    assert moat["tool_integration_score"] >= 0.0
    assert moat["data_flywheel_score"] >= 0.0
    assert moat["estimated_replication_months"] > 0
    assert moat["estimated_replication_cost_usd"] > 0
    assert len(moat["verdict_summary"]) > 20

def test_defensibility_scenario_j_self_hosted_moat(db_session):
    synth_j = generate_synthetic_scenario(db_session, scenario_name="scenario_j", sample_size=80, seed=42)
    moat_j = analyze_defensibility_and_moat(db_session, synth_j["company_id"])
    
    # Scenario J has 90% self-hosted weights, so sovereignty score should be high
    assert moat_j["weight_sovereignty_score"] >= 15.0
    assert moat_j["breakdown"]["self_hosted_llm_ratio_pct"] >= 80.0

def test_defensibility_zero_traces(db_session):
    moat = analyze_defensibility_and_moat(db_session, "non-existent-company")
    assert moat["moat_score"] == 0.0
    assert moat["moat_classification"] == "COMMODITY_WRAPPER"
    assert moat["estimated_replication_months"] == 1.0
