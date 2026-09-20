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

    # --- Local AI (Ollama) ---
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"
    OLLAMA_TIMEOUT_SECONDS: float = 60.0
    # When true (default), well-defined financial intents (balance questions,
    # "I paid X for Y with A and B", "settle ...") are parsed and executed by
    # deterministic backend code, and the reply text is rendered from backend
    # data. The local model handles everything else. Set to false to send
    # every message through the model's tool-calling loop instead.
    AI_DETERMINISTIC_INTENTS: bool = True
    # How long an AI-prepared draft stays confirmable.
    AI_DRAFT_TTL_MINUTES: int = 15


settings = Settings()
