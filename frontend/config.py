"""Frontend configuration — loaded from environment / .env file."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    backend_url: str = "http://localhost:8000"
    request_timeout_seconds: int = 180
    log_stream_poll_interval_ms: int = 2000
    max_log_lines: int = 200

    # Paths as seen by the backend process (not the frontend container).
    comparison_pdf_path: str = "/app/samples/FDS_PriceBook_V0.pdf"
    comparison_docx_path: str = "/app/samples/FDS_PriceBook_V5.docx"


_instance: Settings | None = None


def get_settings() -> Settings:
    global _instance
    if _instance is None:
        _instance = Settings()
    return _instance