import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.ingestion.synthetic import generate_synthetic_scenario
from app.analysis.stress_test import simulate_stress_test_economics

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_stress_test_baseline_vs_stressed(db_session):
    synth = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=80, seed=42)
    company_id = synth["company_id"]
    
    res = simulate_stress_test_economics(
        db_session, company_id,
        volume_multiplier=5.0,
        provider_price_shock_pct=25.0,
        human_hourly_wage_usd=30.0,
        target_customer_price_per_task_usd=0.05
    )
    
    assert "baseline_economics" in res
    assert "stressed_economics" in res
    assert "sensitivity_grids" in res
    assert "vulnerability_verdict" in res
    
    base = res["baseline_economics"]
    strsd = res["stressed_economics"]
    
    assert base["monthly_tasks"] == 50000
    assert strsd["monthly_tasks"] == 250000
    assert strsd["llm_cost_per_task_usd"] > base["llm_cost_per_task_usd"]
    assert strsd["fully_loaded_cost_per_task_usd"] > strsd["llm_cost_per_task_usd"]
    
    # Check sensitivity grids structure
    grids = res["sensitivity_grids"]
    assert len(grids["volume_and_price_shock_margins"]) == 3
    assert len(grids["hir_and_wage_margins"]) == 3
    assert res["vulnerability_verdict"]["status"] in [
        "NEGATIVE_UNIT_MARGIN_HAZARD", "MARGIN_COMPRESSION_RISK", "SUSTAINABLE_SOFTWARE_MARGINS", "HIGH_MARGIN_EXPANSION_CAPABLE"
    ]

def test_stress_test_high_margin_scenario_b(db_session):
    # Scenario B has 96% autonomy and low cost
    synth = generate_synthetic_scenario(db_session, scenario_name="scenario_b", sample_size=80, seed=42)
    res = simulate_stress_test_economics(
        db_session, synth["company_id"],
        volume_multiplier=1.0,
        provider_price_shock_pct=0.0,
        human_hourly_wage_usd=25.0,
        target_customer_price_per_task_usd=0.50 # generous pricing
    )
    assert res["stressed_economics"]["gross_margin_pct"] > 60.0
