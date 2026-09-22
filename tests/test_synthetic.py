import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.ingestion.synthetic import generate_synthetic_scenario
from app.analysis.intervention import analyze_human_intervention
from app.analysis.economics import analyze_unit_economics
from app.analysis.dependency import analyze_provider_dependencies

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_synthetic_scenario_a_benchmark(db_session):
    res = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=100)
    assert res["total_traces"] == 100
    assert res["autonomous_traces"] > 0
    assert res["human_traces"] > 0
    
    interv = analyze_human_intervention(db_session, res["company_id"])
    assert interv["total_traces"] == 100
    assert interv["human_intervention_rate_pct"] > 0
    
    econ = analyze_unit_economics(db_session, res["company_id"])
    assert econ["total_tasks"] == 100
    assert econ["telemetry_attributable_cost_per_task_usd"] > 0
    
    dep = analyze_provider_dependencies(db_session, res["company_id"])
    assert dep["hhi_score"] > 0
