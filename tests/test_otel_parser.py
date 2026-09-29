import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.db.models import Company, Tenant, CostStatus, InterventionDetectionMethod
from app.ingestion.otel import process_otlp_payload

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    tenant = Tenant(name="Test Tenant")
    session.add(tenant)
    session.flush()
    company = Company(tenant_id=tenant.id, name="Test Company")
    session.add(company)
    session.commit()
    yield session
    session.close()

def test_otel_parser_standard_payload(db_session):
    company = db_session.query(Company).first()
    payload = {
        "trace_id": "trace-101",
        "name": "support_agent_workflow",
        "spans": [
            {
                "span_id": "span-1",
                "kind": "llm",
                "start_time": "2026-09-22T10:00:00Z",
                "end_time": "2026-09-22T10:00:02Z",
                "attributes": {
                    "gen_ai.system": "openai",
                    "gen_ai.request.model": "gpt-4o",
                    "gen_ai.usage.prompt_tokens": 500,
                    "gen_ai.usage.completion_tokens": 150
                }
            }
        ]
    }
    trace = process_otlp_payload(db_session, company.id, payload)
    assert trace.id == "trace-101"
    assert len(trace.spans) == 1
    assert trace.total_cost > 0
    assert trace.spans[0].cost_status == CostStatus.MEASURED

def test_otel_parser_unpriced_custom_model(db_session):
    company = db_session.query(Company).first()
    payload = {
        "trace_id": "trace-102",
        "spans": [
            {
                "span_id": "span-2",
                "kind": "llm",
                "start_time": "2026-09-22T10:00:00Z",
                "end_time": "2026-09-22T10:00:02Z",
                "attributes": {
                    "gen_ai.system": "custom_cloud",
                    "gen_ai.request.model": "unpriced-custom-llm-v1",
                    "gen_ai.usage.prompt_tokens": 500,
                    "gen_ai.usage.completion_tokens": 150
                }
            }
        ]
    }
    trace = process_otlp_payload(db_session, company.id, payload)
    assert trace.has_unpriced_model is True
    assert trace.spans[0].cost_status == CostStatus.UNKNOWN

def test_otel_parser_explicit_vs_heuristic_intervention(db_session):
    company = db_session.query(Company).first()
    payload = {
        "trace_id": "trace-103",
        "spans": [
            {
                "span_id": "span-3a",
                "kind": "human",
                "name": "human_approval",
                "start_time": "2026-09-22T10:00:00Z",
                "end_time": "2026-09-22T10:00:10Z"
            },
            {
                "span_id": "span-3b",
                "kind": "agent",
                "name": "tool_execution",
                "latency_gap_seconds": 450,
                "start_time": "2026-09-22T10:00:10Z",
                "end_time": "2026-09-22T10:08:00Z"
            }
        ]
    }
    trace = process_otlp_payload(db_session, company.id, payload)
    assert trace.has_human_intervention is True
    methods = [s.detection_method for s in trace.spans if s.is_human_intervention]
    assert InterventionDetectionMethod.OBSERVED_TELEMETRY in methods
    assert InterventionDetectionMethod.INFERRED_HEURISTIC_LATENCY in methods
