"""
Pydantic-схемы для транскрибации.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TranscriptionOptions(BaseModel):
    """Опции обработки. Передаются клиентом при создании задачи."""

    translate: bool = Field(
        default=False,
        description=(
            "Переводить речь на английский. "
            "Whisper умеет только EN; для других языков нужен отдельный шаг."
        ),
    )
    diarize: bool = Field(
        default=False,
        description=(
            "Разделить по спикерам (SPEAKER_01, SPEAKER_02, ...). "
            "Требует настроенный HF_TOKEN — см. README."
        ),
    )
    language: str | None = Field(
        default=None,
        description=(
            "Принудительно указать язык (ISO-код: ru, en, de, ...). "
            "Если не указан, определяется автоматически."
        ),
    )
    model: str | None = Field(
        default=None,
        description=(
            "Имя Whisper-модели для этой задачи. Если None — берётся "
            "значение WHISPER_MODEL из настроек. Список допустимых моделей: "
            "см. config.AVAILABLE_MODELS."
        ),
    )


class Segment(BaseModel):
    """Один сегмент транскрипта — короткий фрагмент речи с таймкодами."""

    start: float = Field(..., description="Начало в секундах")
    end: float = Field(..., description="Конец в секундах")
    text: str = Field(..., description="Распознанный текст")
    speaker: str | None = Field(
        default=None,
        description="Метка спикера (если диаризация была включена)",
    )


class TranscriptionResult(BaseModel):
    """Полный результат транскрибации одного файла."""

    # Pydantic по умолчанию резервирует префикс "model_" под свои нужды
    # (model_config, model_dump, ...). У нас поле называется model_used —
    # это не конфликт, но Pydantic по привычке предупреждает.
    # Отключаем защищённые namespace локально для этой модели.
    model_config = ConfigDict(protected_namespaces=())

    language: str = Field(..., description="Определённый или заданный язык")
    duration_sec: float = Field(..., description="Длительность аудио в секундах")
    processing_sec: float = Field(..., description="Время обработки в секундах")
    segments: list[Segment] = Field(..., description="Сегменты с таймкодами")
    translated: bool = Field(
        default=False,
        description="True, если текст — это перевод на английский",
    )
    model_used: str | None = Field(
        default=None,
        description="Имя модели, которая использовалась для этой транскрибации",
    )

    @property
    def full_text(self) -> str:
        return " ".join(seg.text.strip() for seg in self.segments)
