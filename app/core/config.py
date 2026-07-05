from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = "API Monitor"
    ENVIRONMENT: str = "local"
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"


# Module-level singleton.
# Validated once on first import. Fails loudly if DATABASE_URL is missing.
settings = Settings()
