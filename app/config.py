import os

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Agentic Diligence"
    PROJECT_SLOGAN: str = "Verify what AI systems actually do—not what they're claimed to do."
    VERSION: str = "0.1.0"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./agentic_diligence.db")
    
    # Model Pricing Defaults (v2026_09) - Cost per 1k tokens
    OPENAI_GPT4O_PROMPT_COST: float = 0.0025
    OPENAI_GPT4O_COMPLETION_COST: float = 0.0100
    OPENAI_GPT4O_MINI_PROMPT_COST: float = 0.00015
    OPENAI_GPT4O_MINI_COMPLETION_COST: float = 0.0006
    ANTHROPIC_CLAUDE_SONNET_PROMPT_COST: float = 0.0030
    ANTHROPIC_CLAUDE_SONNET_COMPLETION_COST: float = 0.0150
    LOCAL_LLAMA3_PROMPT_COST: float = 0.0002
    LOCAL_LLAMA3_COMPLETION_COST: float = 0.0004
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
