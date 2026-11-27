"""Application configuration loaded from environment and repository root .env."""

import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings for Purvai backend."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    purvai_mode: Literal["local", "demo"] = "local"
    database_path: str | None = None
    cors_dev_origin: str = "http://localhost:5173"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    rate_limit_per_minute: int = 120
    trust_proxy_headers: bool = False
    cpcb_timeout_s: float = Field(default=20.0, ge=5.0, le=60.0)
    purvai_fake_providers: bool = False
    co2_estimates_enabled: bool = True

    data_gov_in_api_key: SecretStr | None = None
    ai_provider: str = "gemini"
    ai_model: str = "gemini-3.5-flash-lite"
    ai_fallback_provider: str = "groq"
    ai_fallback_model: str = "openai/gpt-oss-20b"
    ai_timeout_s: float = Field(default=15.0, ge=5.0, le=30.0)
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None

    @field_validator(
        "database_path",
        "data_gov_in_api_key",
        "gemini_api_key",
        "groq_api_key",
        mode="before",
    )
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator("ai_model", mode="before")
    @classmethod
    def _default_ai_model(cls, value: object) -> str:
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return "gemini-3.5-flash-lite"
        return str(value).strip()

    @property
    def resolved_database_path(self) -> Path:
        """Resolve SQLite path relative to repository root or OS temp dir in demo mode."""
        if self.database_path is not None:
            candidate = Path(self.database_path)
            if not candidate.is_absolute():
                return (REPO_ROOT / candidate).resolve()
            return candidate.resolve()
        if self.purvai_mode == "demo":
            return (Path(tempfile.gettempdir()) / "purvai.db").resolve()
        return (REPO_ROOT / "data" / "purvai.db").resolve()


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
