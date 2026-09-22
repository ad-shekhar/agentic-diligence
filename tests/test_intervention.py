import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.ingestion.synthetic import generate_synthetic_scenario
from app.analysis.intervention import analyze_human_intervention

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_intervention_invariant_property(db_session):
    res = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=100)
    interv = analyze_human_intervention(db_session, res["company_id"])
    
    # INVARIANT: autonomous_rate_pct + human_intervention_rate_pct == 100.0
    total_rate = interv["autonomous_rate_pct"] + interv["human_intervention_rate_pct"]
    assert pytest.approx(total_rate, 0.01) == 100.0
    
    # INVARIANT: autonomous_traces + human_traces == total_traces
    assert interv["autonomous_traces"] + interv["human_traces"] == interv["total_traces"]

def test_intervention_zero_traces(db_session):
    interv = analyze_human_intervention(db_session, "non-existent-company")
    assert interv["total_traces"] == 0
    assert interv["autonomous_rate_pct"] == 0.0
    assert interv["human_intervention_rate_pct"] == 0.0

def test_intervention_high_human_scenario(db_session):
    res = generate_synthetic_scenario(db_session, scenario_name="scenario_c", sample_size=100)
    interv = analyze_human_intervention(db_session, res["company_id"])
    assert interv["human_intervention_rate_pct"] > 70.0
