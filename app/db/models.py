import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Float, Integer, Boolean, DateTime, ForeignKey, Enum as SQLEnum, JSON
)
from sqlalchemy.orm import relationship
import enum

from app.db.session import Base

def generate_uuid():
    return str(uuid.uuid4())

class ConfidenceLevel(str, enum.Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    UNVERIFIED = "Unverified"

class VerificationStatus(str, enum.Enum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

class EvidenceType(str, enum.Enum):
    OBSERVED_FACT = "[OF]"       # Observed Fact
    DERIVED_METRIC = "[DM]"      # Derived Metric
    MODEL_INFERENCE = "[MI]"     # Model Inference
    ASSUMPTION = "[AS]"          # Assumption
    USER_CLAIM = "[UC]"          # User-Provided Claim

class CostStatus(str, enum.Enum):
    MEASURED = "MEASURED"
    ESTIMATED = "ESTIMATED"
    UNKNOWN = "UNKNOWN"
    NOT_ESTABLISHED = "NOT_ESTABLISHED"

class InterventionDetectionMethod(str, enum.Enum):
    OBSERVED_TELEMETRY = "OBSERVED_TELEMETRY"
    WORKFLOW_STATE = "WORKFLOW_STATE"
    APPLICATION_EVENT = "APPLICATION_EVENT"
    INFERRED_HEURISTIC_LATENCY = "INFERRED_HEURISTIC_LATENCY"

class Tenant(Base):
    __tablename__ = "tenants"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    companies = relationship("Company", back_populates="tenant", cascade="all, delete-orphan")

class Company(Base):
    __tablename__ = "companies"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    name = Column(String(255), nullable=False)
    domain = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    tenant = relationship("Tenant", back_populates="companies")
    agents = relationship("Agent", back_populates="company", cascade="all, delete-orphan")
    workflows = relationship("Workflow", back_populates="company", cascade="all, delete-orphan")
    traces = relationship("Trace", back_populates="company", cascade="all, delete-orphan")
    claims = relationship("Claim", back_populates="company", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="company", cascade="all, delete-orphan")

class DataSource(Base):
    __tablename__ = "data_sources"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    name = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

class Service(Base):
    __tablename__ = "services"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    name = Column(String(255), nullable=False)
    environment = Column(String(50), default="production")
    created_at = Column(DateTime, default=datetime.utcnow)

class ModelProvider(Base):
    __tablename__ = "model_providers"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, unique=True)
    is_external = Column(Boolean, default=True)

class Model(Base):
    __tablename__ = "models"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    provider_id = Column(String(36), ForeignKey("model_providers.id"), nullable=False)
    name = Column(String(255), nullable=False)
    prompt_cost_per_1k = Column(Float, default=0.0)
    completion_cost_per_1k = Column(Float, default=0.0)

class Agent(Base):
    __tablename__ = "agents"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    name = Column(String(255), nullable=False)
    role = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    framework = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    company = relationship("Company", back_populates="agents")
    spans = relationship("Span", back_populates="agent")

class Workflow(Base):
    __tablename__ = "workflows"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    company = relationship("Company", back_populates="workflows")
    traces = relationship("Trace", back_populates="workflow")

class Trace(Base):
    __tablename__ = "traces"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    workflow_id = Column(String(36), ForeignKey("workflows.id"), nullable=True)
    name = Column(String(255), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    duration_ms = Column(Float, nullable=False)
    status_code = Column(String(50), default="OK")
    has_human_intervention = Column(Boolean, default=False)
    total_cost = Column(Float, default=0.0)
    has_unpriced_model = Column(Boolean, default=False)
    provenance_hash = Column(String(64), nullable=True) # SHA-256 digest of original trace payload
    
    company = relationship("Company", back_populates="traces")
    workflow = relationship("Workflow", back_populates="traces")
    spans = relationship("Span", back_populates="trace", cascade="all, delete-orphan")
    cost_events = relationship("CostEvent", back_populates="trace", cascade="all, delete-orphan")

class Span(Base):
    __tablename__ = "spans"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    trace_id = Column(String(36), ForeignKey("traces.id"), nullable=False)
    parent_span_id = Column(String(36), nullable=True)
    agent_id = Column(String(36), ForeignKey("agents.id"), nullable=True)
    name = Column(String(255), nullable=False)
    span_kind = Column(String(50), nullable=False) # agent, llm, tool, evaluation, human
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    duration_ms = Column(Float, nullable=False)
    
    # GenAI Semantic Conventions
    gen_ai_system = Column(String(100), nullable=True)
    gen_ai_model = Column(String(100), nullable=True)
    gen_ai_prompt_tokens = Column(Integer, default=0)
    gen_ai_completion_tokens = Column(Integer, default=0)
    
    # Tool & Execution Execution
    tool_name = Column(String(100), nullable=True)
    is_error = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    
    # Human Intervention indicators
    is_human_intervention = Column(Boolean, default=False)
    human_action_type = Column(String(100), nullable=True)
    human_reaction_time_ms = Column(Float, nullable=True)
    detection_method = Column(SQLEnum(InterventionDetectionMethod), default=InterventionDetectionMethod.OBSERVED_TELEMETRY)
    
    # Cost
    cost = Column(Float, default=0.0)
    cost_status = Column(SQLEnum(CostStatus), default=CostStatus.MEASURED)
    
    attributes_json = Column(JSON, nullable=True)
    
    trace = relationship("Trace", back_populates="spans")
    agent = relationship("Agent", back_populates="spans")

class HumanIntervention(Base):
    __tablename__ = "human_interventions"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    trace_id = Column(String(36), ForeignKey("traces.id"), nullable=False)
    span_id = Column(String(36), ForeignKey("spans.id"), nullable=False)
    intervention_type = Column(String(50), nullable=False)
    reaction_time_seconds = Column(Float, nullable=False)
    detected_via = Column(SQLEnum(InterventionDetectionMethod), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class CostEvent(Base):
    __tablename__ = "cost_events"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    trace_id = Column(String(36), ForeignKey("traces.id"), nullable=False)
    span_id = Column(String(36), ForeignKey("spans.id"), nullable=True)
    cost_category = Column(String(50), nullable=False) # inference, evaluation, tool, search
    provider_name = Column(String(100), nullable=False)
    model_name = Column(String(100), nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, nullable=False)
    cost_status = Column(SQLEnum(CostStatus), default=CostStatus.MEASURED)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    trace = relationship("Trace", back_populates="cost_events")

class Claim(Base):
    __tablename__ = "claims"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    category = Column(String(100), nullable=False) # autonomy, economics, dependency, evaluation
    claim_text = Column(Text, nullable=False)
    source = Column(String(255), nullable=False)
    target_value = Column(String(255), nullable=True)
    observed_value = Column(String(255), nullable=True)
    verification_status = Column(SQLEnum(VerificationStatus), default=VerificationStatus.INSUFFICIENT_EVIDENCE)
    verification_reason = Column(Text, nullable=True)
    confidence = Column(SQLEnum(ConfidenceLevel), default=ConfidenceLevel.UNVERIFIED)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    company = relationship("Company", back_populates="claims")
    evidence_records = relationship("EvidenceRecord", back_populates="claim", cascade="all, delete-orphan")

class EvidenceRecord(Base):
    __tablename__ = "evidence_records"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    claim_id = Column(String(36), ForeignKey("claims.id"), nullable=True)
    evidence_code = Column(String(50), nullable=False)
    evidence_type = Column(SQLEnum(EvidenceType), nullable=False)
    confidence = Column(SQLEnum(ConfidenceLevel), nullable=False)
    claim_summary = Column(Text, nullable=False)
    observed_fact = Column(Text, nullable=False)
    derived_metric_summary = Column(Text, nullable=True)
    inference_summary = Column(Text, nullable=True)
    verification_status = Column(SQLEnum(VerificationStatus), nullable=True)
    data_source_description = Column(Text, nullable=False)
    sample_size = Column(Integer, default=0)
    verification_method = Column(Text, nullable=False)
    observation_window = Column(String(255), nullable=True)
    pricing_version = Column(String(100), default="v2026_09")
    limitations = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    claim = relationship("Claim", back_populates="evidence_records")

class DependencyRisk(Base):
    __tablename__ = "dependency_risks"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    provider_name = Column(String(100), nullable=False)
    traffic_share = Column(Float, nullable=False)
    cost_share = Column(Float, nullable=False)
    risk_level = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)

class Report(Base):
    __tablename__ = "reports"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=False)
    title = Column(String(255), nullable=False)
    report_type = Column(String(100), default="technical_due_diligence")
    summary_json = Column(JSON, nullable=True)
    pdf_path = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    company = relationship("Company", back_populates="reports")
