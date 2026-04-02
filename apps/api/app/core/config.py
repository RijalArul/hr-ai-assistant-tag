from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from pathlib import Path

# .env lives at the monorepo root (two levels above apps/api/)
_ROOT_ENV = str(Path(__file__).resolve().parents[4] / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT_ENV,
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
    minimax_api_base: str = "https://api.minimaxi.chat/v1"

    # Discord
    discord_application_id: str
    discord_public_key: str
    discord_bot_token: str = ""

    # Gemini (file extraction)
    gemini_api_key: str
    gemini_model: str = "gemini-2.5-flash"

    # HuggingFace Embeddings
    huggingface_api_key: str
    embedding_model: str = "intfloat/multilingual-e5-large"

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # App
    app_env: str = "development"
    app_debug: bool = False
    cors_origins: str = "http://localhost:3000"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
