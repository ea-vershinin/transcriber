"""
Конфигурация приложения.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Список моделей, которые реально предлагаем в UI и API.
# Добавлять сюда новые — и сервер, и клиент сами подхватят.
AVAILABLE_MODELS: tuple[str, ...] = (
    "base",
    "small",
    "medium",
    "large-v3-turbo",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Пути ---
    project_root: Path = Path(__file__).resolve().parent.parent.parent
    uploads_dir: Path = project_root / "storage" / "uploads"
    outputs_dir: Path = project_root / "storage" / "outputs"

    # --- Whisper ---
    # Дефолтная модель. Пользователь может переопределить в каждой задаче.
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_batch_size: int = 4
    # Сколько ASR-моделей держать в RAM одновременно.
    # При превышении вытесняется наименее давно использованная (LRU).
    whisper_cache_size: int = 2

    # --- Диаризация ---
    hf_token: str | None = None

    # --- Ограничения ---
    max_upload_mb: int = 500


settings = Settings()
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
settings.outputs_dir.mkdir(parents=True, exist_ok=True)
