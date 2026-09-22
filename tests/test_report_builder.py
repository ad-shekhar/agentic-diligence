import pytest
import os
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

def test_report_builder_pdf_and_json(db_session, tmp_path):
    res = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=50)
    pdf_file = str(tmp_path / "test_report.pdf")
    
    report_data = build_due_diligence_report(db_session, res["company_id"], pdf_output_path=pdf_file)
    
    assert os.path.exists(pdf_file)
    assert report_data["company"]["name"] == "AcmeAI Target (SCENARIO_A)"
    assert len(report_data["claims"]) == 3
    assert len(report_data["evidence_records"]) == 4
    assert len(report_data["limitations"]) > 0
    assert report_data["report_metadata"]["version"] == "0.1.0-hardened"
