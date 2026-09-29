import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.ingestion.synthetic import generate_synthetic_scenario
from app.analysis.memo import generate_investment_committee_memo

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_generate_investment_committee_memo(db_session):
    synth = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=80, seed=42)
    company_id = synth["company_id"]
    
    memo = generate_investment_committee_memo(db_session, company_id)
    
    assert "diligence_risk_score" in memo
    assert 0.0 <= memo["diligence_risk_score"] <= 100.0
    assert memo["deal_verdict"] in [
        "RECOMMENDED", "CONDITIONAL_REMEDIATION_REQUIRED", "HIGH_RISK_CAUTION", "DO_NOT_PROCEED"
    ]
    assert len(memo["executive_verdict_summary"]) > 20
    assert "flags_summary" in memo
    assert "red_flags" in memo
    assert "yellow_flags" in memo
    assert "green_flags" in memo
    assert len(memo["remediation_playbook"]) == 4

def test_memo_scenario_c_dealbreakers(db_session):
    # Scenario C has contradicted pitch deck claims & cost blowouts
    synth_c = generate_synthetic_scenario(db_session, scenario_name="scenario_c", sample_size=80, seed=42)
    memo_c = generate_investment_committee_memo(db_session, synth_c["company_id"])
    
    # Should identify contradicted claim as red flag
    red_categories = [rf["category"] for rf in memo_c["red_flags"]]
    assert "Claim Integrity" in red_categories or "Autonomy" in red_categories or "Unit Economics" in red_categories
    assert memo_c["deal_verdict"] in ["HIGH_RISK_CAUTION", "DO_NOT_PROCEED"]
