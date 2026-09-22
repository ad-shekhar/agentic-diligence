import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.ingestion.synthetic import generate_synthetic_scenario
from app.analysis.economics import analyze_unit_economics

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_economics_latency_invariants(db_session):
    res = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=100)
    econ = analyze_unit_economics(db_session, res["company_id"])
    
    p50 = econ["latency_ms"]["p50"]
    p95 = econ["latency_ms"]["p95"]
    p99 = econ["latency_ms"]["p99"]
    
    # INVARIANT: P95 >= P50 and P99 >= P95
    assert p95 >= p50
    assert p99 >= p95
    assert econ["telemetry_attributable_cost_per_task_usd"] >= 0.0

def test_economics_unknown_pricing_scenario(db_session):
    res = generate_synthetic_scenario(db_session, scenario_name="scenario_h", sample_size=50)
    econ = analyze_unit_economics(db_session, res["company_id"])
    
    assert econ["overall_cost_status"] == "UNKNOWN"
    assert econ["cost_breakdown"]["inference"]["cost_status"] == "UNKNOWN"
