"""Application configuration."""
import json
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/ocr_platform"
    database_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    celery_worker_pool: str = "solo"
    celery_worker_concurrency: int = 1

    # PaddleOCR Service
    paddle_ocr_url: str = "http://172.18.15.244:8888/layout-parsing"
    paddle_ocr_model_name: str = "PaddleOCR-VL-0.9B"
    paddle_ocr_timeout_seconds: int = 1800
    paddle_ocr_connect_timeout_seconds: int = 10
    paddle_ocr_write_timeout_seconds: int = 120
    paddle_ocr_retries: int = 2
    paddle_ocr_retry_backoff_seconds: float = 1.0
    paddle_ocr_trust_env: bool = False
    paddle_ocr_max_concurrency: int = 1
    paddle_ocr_max_file_mb: int = 200
    paddle_ocr_max_pixels: int = 2048 * 2048
    paddle_ocr_max_new_tokens: int = 4096

    # GPT Service
    gpt_api_key: str = ""
    gpt_base_url: str = "https://api.siliconflow.cn/v1"
    gpt_model: str = "deepseek-ai/DeepSeek-V3"
    gpt_timeout: int = 300
    gpt_max_retries: int = 3  # Increased from 2 to 3 for better TLS fault tolerance
    gpt_retry_backoff_seconds: float = 2.0  # Increased from 1.0 to 2.0 for more stable retries
    gpt_page_max_tokens: int = 8192
    gpt_page_enable_thinking: bool = False
    gpt_structured_output: bool = True

    # Storage paths
    storage_path: str = "../storage"
    upload_path: str = "../storage/uploads"
    pages_path: str = "../storage/pages"
    results_path: str = "../storage/results"
    exports_path: str = "../storage/exports"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # CORS
    cors_origins: str = '["http://localhost:3000","http://127.0.0.1:3000"]'

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from JSON string."""
        return json.loads(self.cors_origins)

    def get_storage_path(self) -> Path:
        """Get absolute storage path."""
        return Path(self.storage_path).resolve()

    def get_upload_path(self) -> Path:
        """Get absolute upload path."""
        return Path(self.upload_path).resolve()

    def get_pages_path(self) -> Path:
        """Get absolute pages path."""
        return Path(self.pages_path).resolve()

    def get_results_path(self) -> Path:
        """Get absolute results path."""
        return Path(self.results_path).resolve()

    def get_exports_path(self) -> Path:
        """Get absolute exports path."""
        return Path(self.exports_path).resolve()

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
