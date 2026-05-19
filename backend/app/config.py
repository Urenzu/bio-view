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

    # AWS — only required for ingest (S3 reads of bioRxiv/medRxiv buckets).
    # Empty defaults let the API container boot on hosts that never run ingest.
    aws_access_key: str = Field(default="", alias="AWS_ACCESS_KEY")
    aws_secret_access_key: str = Field(default="", alias="AWS_SECRET_ACCESS_KEY")
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
    embedding_model_id: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    gen_model_id: str = "qwen/qwen3-30b-a3b-instruct-2507"

    # API keys
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # Database — Postgres with pgvector. DATABASE_URL must point at a Postgres
    # instance with the vector extension available.
    database_url_override: str = Field(
        default="postgresql://bioview:bioview@localhost:5432/bioview",
        alias="DATABASE_URL",
    )

    # Auth — SECRET_KEY signs JWT sessions; Google OAuth for login
    secret_key: str = Field(default="dev-secret-change-in-production", alias="SECRET_KEY")
    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(
        default="http://localhost:8000/auth/google/callback",
        alias="GOOGLE_REDIRECT_URI",
    )

    # Local file storage. On Railway / read-only filesystems point these at
    # an ephemeral location like /tmp via env vars.
    jats_cache_path: Path = Field(
        default=PROJECT_ROOT / "data" / "jats", alias="JATS_CACHE_PATH"
    )
    meca_temp_path: Path = Field(
        default=PROJECT_ROOT / "data" / "meca_tmp", alias="MECA_TEMP_PATH"
    )

    # Scheduling
    poll_cron: str = "0 6 1 * *"  # 06:00 UTC, 1st of each month

    # Retrieval
    chunk_max_chars: int = 2000
    chunk_overlap_chars: int = 200
    retrieval_top_k: int = 50
    result_min_k: int = 2
    result_max_k: int = 15
    # Fractional score floor: drop hits below (1 - score_floor) * top_score.
    # Scale-invariant, so works for cosine similarity and RRF scores alike.
    # 0.15 = "keep hits within 15% of the top score". Tune empirically.
    score_floor: float = 0.15

    @property
    def database_url(self) -> str:
        return self.database_url_override


settings = Settings()

for _p in [settings.jats_cache_path, settings.meca_temp_path]:
    _p.mkdir(parents=True, exist_ok=True)
