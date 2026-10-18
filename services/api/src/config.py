"""Mise API configuration — pydantic-settings reads from env."""

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "", "case_sensitive": False}

    # App
    app_env: str = "dev"

    # Postgres
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "mise"
    postgres_user: str = "mise"
    postgres_password: str = "change_me_in_production"
    sql_echo: bool = False

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = "change_me_in_production"

    # Auth
    owner_api_key: str = "change_me_in_production"
    staff_pin: str = "0000"

    # URLs
    public_guest_url: str = "http://localhost:3000"
    public_owner_url: str = "http://localhost:3001"

    # Inference — provider routing
    llm_provider: str = "mock"  # "mock" | "amd"
    llm_api_key: str = ""  # stripped on load; NEVER log or return
    llm_base_url: str = "http://inference:8080/v1"
    llm_model: str = "mock-llm"
    llm_model_fallbacks: list[str] = []  # ordered fallback list
    llm_max_tokens: int = 1024
    llm_timeout_seconds: int = 30
    vlm_base_url: str = "http://inference:8080/v1"
    vlm_model: str = "mock-vlm"
    vlm_model_fallbacks: list[str] = []

    # Rate limiting
    llm_global_rpm: int = 15  # safe below AMD's 20 RPM limit
    guest_chat_limit: int = 10  # per-session message cap

    # Mock control
    mock_latency_ms: int = 100
    mock_error_rate: float = 0.0
    mock_timeout_ms: int = 0

    # Demo
    demo_mode: bool = False
    demo_restaurant_slug: str = "trattoria-da-mario"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync URL for Alembic migrations (psycopg)."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @field_validator("llm_api_key", mode="before")
    @classmethod
    def _strip_api_key(cls, v: str) -> str:
        """Strip ALL whitespace from the API key (copy-paste safety)."""
        return "".join(v.split()) if isinstance(v, str) else v

    @model_validator(mode="after")
    def reject_default_secrets_in_non_dev(self) -> "Settings":
        if self.app_env == "dev":
            return self

        defaults = {
            "api_secret_key": "change_me_in_production",
            "owner_api_key": "change_me_in_production",
            "staff_pin": "0000",
            "postgres_password": "change_me_in_production",
        }
        for field, default_val in defaults.items():
            if getattr(self, field) == default_val:
                raise ValueError(f"{field.upper()} must be changed when APP_ENV={self.app_env!r}")
        return self


settings = Settings()
