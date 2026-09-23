import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.ingestion.synthetic import generate_synthetic_scenario
from app.aibom.generator import generate_native_aibom, export_cyclonedx_aibom

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_native_aibom_generation(db_session):
    res = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=40, seed=42)
    company_id = res["company_id"]
    
    aibom = generate_native_aibom(db_session, company_id)
    
    assert aibom.company_id == company_id
    assert aibom.total_traces_analyzed == 40
    assert len(aibom.models) > 0
    assert any(m.is_primary for m in aibom.models)
    assert aibom.unique_model_count >= 1
    assert len(aibom.tools) > 0
    assert aibom.has_human_checkpoints is True

def test_cyclonedx_export(db_session):
    res = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=30, seed=42)
    company_id = res["company_id"]
    
    native_bom = generate_native_aibom(db_session, company_id)
    cdx = export_cyclonedx_aibom(native_bom)
    
    assert cdx["bomFormat"] == "CycloneDX"
    assert cdx["specVersion"] == "1.6"
    assert "components" in cdx
    assert len(cdx["components"]) > 0
    
    # Check that model component is typed machine-learning-model
    model_comps = [c for c in cdx["components"] if c["type"] == "machine-learning-model"]
    assert len(model_comps) > 0
