import os
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "ReconAI"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./reconai.db")
    
    # AI / LLM Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    
    # Reconciliation Thresholds
    AUTO_MATCH_THRESHOLD: float = 98.0
    HIGH_CONFIDENCE_THRESHOLD: float = 85.0
    REVIEW_THRESHOLD: float = 60.0
    
    # ML Models
    ML_MODEL_PATH: str = os.getenv("ML_MODEL_PATH", "ml/artifacts/matcher_model.joblib")
    
    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()
