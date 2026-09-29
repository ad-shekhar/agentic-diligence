import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.ingestion.synthetic import generate_synthetic_scenario
from app.analysis.evaluation import analyze_evaluation_overhead

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_evaluation_adequate_coverage(db_session):
    res = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=100)
    eval_res = analyze_evaluation_overhead(db_session, res["company_id"])
    
    assert eval_res["eval_coverage_pct"] >= 20.0
    assert eval_res["insufficient_coverage_flag"] is False
    assert eval_res["evaluation_status"] == "ADEQUATE_EVALUATION_COVERAGE"

def test_evaluation_insufficient_coverage_scenario(db_session):
    res = generate_synthetic_scenario(db_session, scenario_name="scenario_g", sample_size=100)
    eval_res = analyze_evaluation_overhead(db_session, res["company_id"])
    
    assert eval_res["eval_coverage_pct"] == 0.0
    assert eval_res["insufficient_coverage_flag"] is True
    assert eval_res["evaluation_status"] == "INSUFFICIENT_EVALUATION_COVERAGE"
