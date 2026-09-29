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

def test_full_diligence_package_generation(db_session, tmp_path):
    res = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=30, seed=42)
    company_id = res["company_id"]
    
    out_dir = str(tmp_path / "package_out")
    pdf_path = str(tmp_path / "package_out" / "custom_report.pdf")
    
    package = build_due_diligence_report(
        db_session,
        company_id=company_id,
        pdf_output_path=pdf_path,
        output_dir=out_dir
    )
    
    assert "package_files" in package
    pkg_files = package["package_files"]
    
    # Ensure all package files were produced on disk
    assert os.path.exists(pkg_files["pdf_report"])
    assert os.path.exists(pkg_files["package_json"])
    assert os.path.exists(pkg_files["audit_manifest"])
    assert os.path.exists(pkg_files["aibom_native"])
    assert os.path.exists(pkg_files["aibom_cyclonedx"])
    
    # Verify contents of package JSON
    with open(pkg_files["package_json"], "r") as f:
        pkg_json = json.load(f)
    assert pkg_json["company"]["id"] == company_id
    assert "aibom" in pkg_json
    assert "cascades" in pkg_json
    assert "audit_manifest" in pkg_json
    assert len(pkg_json["claims"]) == 3
