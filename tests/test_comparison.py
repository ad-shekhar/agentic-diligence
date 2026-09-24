import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.ingestion.synthetic import generate_synthetic_scenario
from app.analysis.comparison import compare_diligence_targets

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_comparative_diligence_engine(db_session):
    synth_a = generate_synthetic_scenario(db_session, scenario_name="scenario_a", sample_size=50, seed=42)
    synth_b = generate_synthetic_scenario(db_session, scenario_name="scenario_d", sample_size=50, seed=99)
    
    comp = compare_diligence_targets(db_session, synth_a["company_id"], synth_b["company_id"])
    
    assert "comparison_title" in comp
    assert "dimension_winners" in comp
    assert "matrix" in comp
    assert len(comp["matrix"]) >= 9
    
    # Check that required dimensions exist in matrix
    dimensions = [row["dimension"] for row in comp["matrix"]]
    assert "True Autonomy Rate" in dimensions
    assert "Unit Economics" in dimensions
    assert "Vendor Concentration" in dimensions
    assert "Failure Cascade Risk" in dimensions
    assert "Tool Risk Score" in dimensions
