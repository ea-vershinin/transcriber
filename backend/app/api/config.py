"""
Публичные настройки для фронтенда:
  GET /api/config/models — список доступных моделей Whisper + дефолт.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import AVAILABLE_MODELS, settings

router = APIRouter(prefix="/api/config", tags=["config"])


class ModelsInfo(BaseModel):
    available: list[str]
    default: str


@router.get("/models", response_model=ModelsInfo)
def get_models() -> ModelsInfo:
    return ModelsInfo(
        available=list(AVAILABLE_MODELS),
        default=settings.whisper_model,
    )
