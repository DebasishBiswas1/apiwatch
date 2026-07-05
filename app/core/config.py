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

    # ── JWT settings ──────────────────────────────────────────────────────────
    # SECRET_KEY: the signing key for all JWTs this server issues.
    # MUST be a long random string in production — never a dictionary word.
    # Anyone with this key can forge valid tokens for any user.
    # We generate it in .env; the default here is for dev only.
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"

    # Algorithm for JWT signing. HS256 = HMAC with SHA-256.
    # Symmetric: same key signs and verifies. Fine for a single-server SaaS.
    # For multi-service architectures you would use RS256 (asymmetric).
    ALGORITHM: str = "HS256"

    # How long a token is valid after issue, in minutes.
    # 60*24*7 = 7 days. Short-lived tokens are more secure but require
    # refresh token logic. 7 days is a pragmatic balance for a SaaS.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7


settings = Settings()
