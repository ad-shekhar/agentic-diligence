import os
import zipfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.ingestion.synthetic import generate_synthetic_scenario
from app.reporting.builder import build_due_diligence_report
from app.reporting.bundle import create_diligence_bundle, verify_diligence_bundle

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_bundle_creation_and_verification(db_session, tmp_path):
    synth = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=50, seed=42)
    company_id = synth["company_id"]
    
    report_data = build_due_diligence_report(db_session, company_id, output_dir=str(tmp_path))
    bundle_path = os.path.join(str(tmp_path), "test_bundle.zip")
    
    # 1. Create Bundle
    created_path = create_diligence_bundle(report_data, bundle_path)
    assert os.path.exists(created_path)
    
    # 2. Verify Valid Bundle
    res = verify_diligence_bundle(created_path)
    assert res["is_valid"] is True
    assert res["status"] == "VERIFIED"
    assert res["total_files_checked"] >= 4
    assert len(res["errors"]) == 0
    
    # 3. Test Tamper Detection
    tampered_bundle_path = os.path.join(str(tmp_path), "tampered_bundle.zip")
    # Read files from original zip and corrupt one file
    with zipfile.ZipFile(created_path, "r") as z_in, zipfile.ZipFile(tampered_bundle_path, "w") as z_out:
        for item in z_in.infolist():
            content = z_in.read(item.filename)
            if item.filename == "diligence_package.json":
                # Corrupt the json file
                content = content + b"\n/* TAMPERED CONTENT INSERTED */\n"
            z_out.writestr(item, content)
            
    tamper_res = verify_diligence_bundle(tampered_bundle_path)
    assert tamper_res["is_valid"] is False
    assert tamper_res["status"] == "TAMPERED"
    assert any("Checksum mismatch for diligence_package.json" in err for err in tamper_res["errors"])
