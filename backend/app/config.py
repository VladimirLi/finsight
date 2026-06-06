"""Application settings, environment-driven (provider-agnostic by design)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven application settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- storage ---
    database_url: str = "sqlite:///./finsight.db"
    upload_dir: str = "./uploads"

    # --- LLM provider selection ---
    # which provider the extraction pipeline uses: "anthropic" | "openai" | "ollama"
    llm_provider: str = "anthropic"
    # model id is per-provider, e.g. "claude-sonnet-4-6", "gpt-4o", "llama3.1:70b"
    llm_model: str = "claude-sonnet-4-6"

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    # OpenAI-compatible base url (also used for vLLM / LM Studio)
    openai_base_url: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # --- OCR ---
    ocr_dpi: int = 200
    tesseract_cmd: str | None = None  # path override if not on PATH

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
