from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All configuration is read from environment variables / the .env file.
    Never hardcode secrets here — this class only defines shape + defaults.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "SplitPay"

    # --- Database ---
    DATABASE_URL: str

    # --- Auth / JWT ---
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # --- Redis (caching) ---
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 30

    # --- Payments ---
    # Sandbox mode gates the /payments/{id}/simulate test endpoint — see
    # app/services/payment_service.py module docstring for why this exists
    # instead of a real gateway integration.
    PAYMENT_SANDBOX_MODE: bool = True
    PAYMENT_WEBHOOK_SECRET: str = "sandbox-webhook-secret-change-me"


settings = Settings()
