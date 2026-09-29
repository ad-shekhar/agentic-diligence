import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.ingestion.synthetic import generate_synthetic_scenario
from app.analysis.cascade import analyze_failure_cascades

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_failure_cascade_analysis(db_session):
    res = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=50, seed=42)
    company_id = res["company_id"]
    
    cascades = analyze_failure_cascades(db_session, company_id)
    
    assert cascades["total_traces_analyzed"] == 50
    assert "cascade_frequency_pct" in cascades
    assert "avg_cost_multiplier_on_failure" in cascades
    assert cascades["avg_cost_multiplier_on_failure"] >= 1.0
    assert len(cascades["economic_impact_statement"]) > 10
