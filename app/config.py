from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    database_url: str
    qdrant_url: str = "http://localhost:6333"
    qdrant_trials_collection: str = "syn_trials"
    qdrant_papers_collection: str = "syn_papers"
    redis_url: str = "redis://localhost:6379"
    ncbi_email: str
    ncbi_api_key: str = ""
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    allowed_origins: list[str] = ["http://localhost:3000"]
    environment: str = "development"
    groq_api_key: str = ""
    qdrant_ema_collection: str = "syn_ema"
    notion_token: str = ""
    notion_reports_db_id: str = ""
    discord_webhook_url: str = ""
    # Vision AI
    vision_provider: str = "groq"
    openai_api_key: str = ""
    vision_max_figures_per_pdf: int = 10
    vision_dpi: int = 150
    qdrant_figures_collection: str = "syn_figures"

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value):
        if isinstance(value, str):
            # Accept both JSON array and comma-separated origins.
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
