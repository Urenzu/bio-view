from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # AWS
    aws_access_key: str = Field(alias="AWS_ACCESS_KEY")
    aws_secret_access_key: str = Field(alias="AWS_SECRET_ACCESS_KEY")
    aws_region: str = "us-east-1"

    # Sources
    biorxiv_bucket: str = "biorxiv-src-monthly"
    medrxiv_bucket: str = "medrxiv-src-monthly"
    biorxiv_prefix: str = "Current_Content/"
    medrxiv_prefix: str = "Current_Content/"
    earliest_year: int = 2026
    max_daily_gb: float = 50.0
    max_retry_attempts: int = 3

    # Models
    embedding_model_id: str = "NeuML/pubmedbert-base-embeddings"
    embedding_dim: int = 768
    reranker_model_id: str = "ncbi/MedCPT-Cross-Encoder"
    gen_model_id: str = "qwen/qwen3-30b-a3b-instruct-2507"

    # OpenRouter
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")

    # Database — set DATABASE_URL env var for Postgres, falls back to local SQLite
    database_url_override: str = Field(default="", alias="DATABASE_URL")
    sqlite_path: Path = PROJECT_ROOT / "data" / "bio_view.db"

    # Qdrant — set QDRANT_URL / QDRANT_API_KEY for remote, defaults to local
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_api_key: str = Field(default="", alias="QDRANT_API_KEY")

    # Auth — SECRET_KEY signs JWT sessions; Google OAuth for login
    secret_key: str = Field(default="dev-secret-change-in-production", alias="SECRET_KEY")
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(
        default="http://localhost:8000/auth/google/callback",
        alias="GOOGLE_REDIRECT_URI",
    )

    # Local file storage
    jats_cache_path: Path = PROJECT_ROOT / "data" / "jats"
    meca_temp_path: Path = PROJECT_ROOT / "data" / "meca_tmp"

    # Scheduling
    poll_cron: str = "0 6 1 * *"  # 06:00 UTC, 1st of each month

    # Retrieval
    chunk_max_chars: int = 2000
    chunk_overlap_chars: int = 200
    retrieval_top_k: int = 50
    rerank_min_k: int = 2
    rerank_max_k: int = 15
    rerank_score_floor: float = 4.0

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return f"sqlite:///{self.sqlite_path}"


settings = Settings()

for _p in [
    settings.sqlite_path.parent,
    settings.jats_cache_path,
    settings.meca_temp_path,
]:
    _p.mkdir(parents=True, exist_ok=True)
