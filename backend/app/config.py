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
    reranker_model_id: str = "ncbi/MedCPT-Cross-Encoder"
    gen_model_id: str = "qwen/qwen3-30b-a3b-instruct-2507"

    # OpenRouter
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")

    # Storage paths
    chroma_path: Path = PROJECT_ROOT / "data" / "chroma"
    sqlite_path: Path = PROJECT_ROOT / "data" / "bio_view.db"
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
        return f"sqlite:///{self.sqlite_path}"


settings = Settings()

for _p in [
    settings.chroma_path,
    settings.sqlite_path.parent,
    settings.jats_cache_path,
    settings.meca_temp_path,
]:
    _p.mkdir(parents=True, exist_ok=True)
