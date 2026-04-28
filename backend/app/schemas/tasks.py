"""
Pydantic-схемы для фоновых задач транскрибации.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.transcription import TranscriptionResult


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskSource(str, Enum):
    UPLOAD = "upload"       # через HTTP POST
    YOUTUBE = "youtube"     # с YouTube
    LOCAL = "local"         # локальный файл/папка — мы читаем с диска по пути


class AutoExportFormat(str, Enum):
    """Форматы, которые можно автоматически сохранить рядом с исходником."""
    TXT = "txt"
    SRT = "srt"
    VTT = "vtt"
    JSON = "json"
    DOCX_PLAIN = "docx_plain"
    DOCX_TIMECODED = "docx_timecoded"
    DOCX_FULL = "docx_full"


class Task(BaseModel):
    task_id: str = Field(..., description="Уникальный ID задачи")
    status: TaskStatus
    source: TaskSource
    source_info: str = Field(..., description="Имя файла, URL или путь")
    created_at: datetime
    updated_at: datetime
    result: TranscriptionResult | None = None
    error: str | None = None

    # Для LOCAL-задач: куда сохранять результаты рядом с исходником.
    # Для UPLOAD/YOUTUBE это поле None — результаты скачиваются через API.
    local_source_path: str | None = None
    exported_files: list[str] = Field(
        default_factory=list,
        description="Пути к созданным файлам транскриптов",
    )


class TaskCreated(BaseModel):
    task_id: str
    status: TaskStatus


class BatchCreated(BaseModel):
    """Ответ при старте батчевой обработки папки."""
    task_ids: list[str]
    files_found: int
