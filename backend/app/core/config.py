from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "noesis"
    postgres_user: str = "noesis"
    postgres_password: str = "noesis"

    redis_url: str = "redis://localhost:6379/0"
    notion_api_key: str = ""
    gmail_credentials_path: str = "backend/credentials.json"
    gmail_token_path: str = "backend/token.json"
    api_auth_token: str = "dev-secret-token"
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536
    embedding_batch_size: int = 100
    embedding_rate_limit_rpm: int = 500
    chunk_size: int = 400
    chunk_overlap: int = 50
    chunk_min_chars: int = 100
    vector_similarity_threshold: float = 0.75
    vector_max_results: int = 10
    bm25_weight: float = 0.3
    vector_weight: float = 0.7
    rrf_k: int = 60

    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
