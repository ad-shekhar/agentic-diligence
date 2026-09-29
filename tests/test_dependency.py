import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.ingestion.synthetic import generate_synthetic_scenario
from app.analysis.dependency import analyze_provider_dependencies

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_dependency_hhi_invariants(db_session):
    res = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=100)
    dep = analyze_provider_dependencies(db_session, res["company_id"])
    
    # INVARIANT: HHI score is between 0.0 and 1.0
    assert 0.0 <= dep["hhi_score"] <= 1.0
    
    # INVARIANT: Provider share sum approximately 100.0%
    total_share = sum(p["share_pct"] for p in dep["providers"])
    assert pytest.approx(total_share, 0.1) == 100.0
    
    assert "raw_metrics" in dep
    assert "interpretation" in dep

def test_dependency_high_concentration_scenario(db_session):
    res = generate_synthetic_scenario(db_session, scenario_name="scenario_f", sample_size=100)
    dep = analyze_provider_dependencies(db_session, res["company_id"])
    
    assert dep["hhi_score"] >= 0.60
    assert dep["concentration_level"] == "HIGH_CONCENTRATION"

def test_dependency_balanced_scenario(db_session):
    res = generate_synthetic_scenario(db_session, scenario_name="scenario_i", sample_size=100)
    dep = analyze_provider_dependencies(db_session, res["company_id"])
    
    assert dep["hhi_score"] < 0.60
    assert dep["concentration_level"] in ("MODERATE_CONCENTRATION", "DIVERSIFIED")
