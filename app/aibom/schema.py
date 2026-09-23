from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ModelAsset(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    model_name: str
    provider_name: str
    hosting_type: str = "cloud_api" # "cloud_api" or "self_hosted_weights"
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    measured_cost_usd: float = 0.0
    call_count: int = 0
    is_primary: bool = False
    parameter_tier: Optional[str] = None # e.g. "large", "small", "unspecified"

class ToolAsset(BaseModel):
    tool_name: str
    tool_type: str = "general_tool" # "api", "database", "retrieval", "sandbox"
    call_count: int = 0
    failure_count: int = 0
    failure_rate_pct: float = 0.0
    avg_latency_ms: float = 0.0

class VectorStoreAsset(BaseModel):
    system_name: str # e.g. "pinecone", "chroma", "qdrant", "weaviate"
    embedding_model: Optional[str] = None
    usage_count: int = 0

class ExternalAPIAsset(BaseModel):
    domain_or_service: str
    provider: str
    call_count: int = 0
    error_count: int = 0

class AgentFrameworkAsset(BaseModel):
    framework_name: str # "Custom Orchestrator", "LangChain", "LlamaIndex", etc.
    confidence: str = "Inferred"
    notes: Optional[str] = None

class HumanCheckpointAsset(BaseModel):
    checkpoint_type: str
    detection_method: str
    trigger_count: int = 0
    avg_reaction_time_seconds: float = 0.0

class NativeAIBOM(BaseModel):
    bom_id: str
    generated_at: str
    company_id: str
    company_name: str
    observation_window: str = "Last 30 Days"
    total_traces_analyzed: int = 0
    total_spans_analyzed: int = 0
    
    # Categorized Assets
    models: List[ModelAsset] = Field(default_factory=list)
    tools: List[ToolAsset] = Field(default_factory=list)
    vector_stores: List[VectorStoreAsset] = Field(default_factory=list)
    external_apis: List[ExternalAPIAsset] = Field(default_factory=list)
    frameworks: List[AgentFrameworkAsset] = Field(default_factory=list)
    human_checkpoints: List[HumanCheckpointAsset] = Field(default_factory=list)
    
    # Summary Metrics
    total_model_spend_usd: float = 0.0
    unique_model_count: int = 0
    unique_tool_count: int = 0
    has_self_hosted_models: bool = False
    has_human_checkpoints: bool = False
