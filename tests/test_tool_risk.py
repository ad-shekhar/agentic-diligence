import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.ingestion.synthetic import generate_synthetic_scenario
from app.analysis.tool_risk import classify_tool_privilege, analyze_tool_execution_risk

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_classify_tool_privilege():
    assert classify_tool_privilege("bash_command") == "CRITICAL"
    assert classify_tool_privilege("python_interpreter") == "CRITICAL"
    assert classify_tool_privilege("sql_write_record") == "HIGH"
    assert classify_tool_privilege("delete_file") == "HIGH"
    assert classify_tool_privilege("send_email_notification") == "MEDIUM"
    assert classify_tool_privilege("stripe_charge") == "MEDIUM"
    assert classify_tool_privilege("crm_customer_lookup") == "LOW"
    assert classify_tool_privilege("vector_search") == "LOW"
    assert classify_tool_privilege("") == "LOW"

def test_analyze_tool_execution_risk_synthetic(db_session):
    synth = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=100, seed=42)
    company_id = synth["company_id"]
    
    risk = analyze_tool_execution_risk(db_session, company_id)
    assert "total_tool_calls" in risk
    assert risk["total_tool_calls"] > 0
    assert risk["unique_tools_count"] > 0
    assert "tool_risk_score" in risk
    assert 0.0 <= risk["tool_risk_score"] <= 100.0
    assert risk["risk_level"] in ["LOW", "MODERATE", "ELEVATED", "CRITICAL"]
    assert len(risk["tool_inventory"]) > 0

def test_analyze_tool_execution_risk_zero_traces(db_session):
    risk = analyze_tool_execution_risk(db_session, "non-existent-company")
    assert risk["total_tool_calls"] == 0
    assert risk["tool_risk_score"] == 0.0
    assert risk["risk_level"] == "LOW"
