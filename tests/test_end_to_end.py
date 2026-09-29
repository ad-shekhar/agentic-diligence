import pytest
import os
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.ingestion.synthetic import generate_synthetic_scenario
from app.reporting.builder import build_due_diligence_report

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.mark.parametrize("scenario", [
    "scenario_a",
    "scenario_b",
    "scenario_c",
    "scenario_d",
    "scenario_f",
    "scenario_g",
    "scenario_h",
    "scenario_i",
    "scenario_j"
])
def test_end_to_end_all_scenarios(db_session, tmp_path, scenario):
    res = generate_synthetic_scenario(db_session, scenario_name=scenario, sample_size=30, seed=42)
    pdf_file = str(tmp_path / f"report_{scenario}.pdf")
    
    report_data = build_due_diligence_report(
        db_session, res["company_id"], pdf_output_path=pdf_file, output_dir=str(tmp_path)
    )
    
    assert os.path.exists(pdf_file)
    assert report_data["interventions"]["total_traces"] == res["total_traces"]
    assert "verification_status" in report_data["claims"][0]
    assert len(report_data["evidence_records"]) == 4
