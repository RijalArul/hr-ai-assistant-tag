from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path


def _find_env_file() -> str | None:
    """Walk up from config.py to find the nearest .env file.
    Works both locally (monorepo root) and on Railway (apps/api is root).
    """
    here = Path(__file__).resolve()
    for i in range(2, len(here.parents)):
        candidate = here.parents[i] / ".env"
        if candidate.exists():
            return str(candidate)
    return None


_ROOT_ENV = _find_env_file()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT_ENV,  # None in Railway → reads from env vars directly
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str

    # Redis
    redis_url: str
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_user: str = "default"
    redis_password: str = ""

    # MiniMax LLM
    minimax_api_key: str
    minimax_api_base: str = "https://api.minimaxi.com/v1"
    minimax_model: str = "MiniMax-M2.7"
    minimax_timeout_seconds: int = 20

    # Discord
    discord_application_id: str
    discord_public_key: str
    discord_bot_token: str = ""

    # Gemini
    gemini_api_key: str
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: int = 10
    gemini_classifier_timeout_seconds: int = 20
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_output_dimensionality: int = 1024
    # Deprecated compatibility fields. Kept so older local .env files
    # do not break while embeddings have moved to Gemini.
    huggingface_api_key: str = ""
    embedding_model: str = "intfloat/multilingual-e5-large"

    # S3-compatible object storage
    storage_s3_endpoint_url: str = ""
    storage_s3_bucket_name: str = ""
    storage_s3_access_key_id: str = ""
    storage_s3_secret_access_key: str = ""
    storage_s3_region: str = "auto"
    storage_s3_presign_ttl_seconds: int = 3600
    storage_s3_connect_timeout_seconds: int = 5
    storage_s3_read_timeout_seconds: int = 10

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # In-memory LRU cache
    lru_cache_max_entries: int = 256
    lru_cache_ttl_seconds: int = 900

    # App
    app_env: str = "development"
    app_debug: bool = False
    cors_origins: str = "http://localhost:3000"
    phase3_use_remote_providers: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]
