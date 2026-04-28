"""
Эндпоинты просмотра задач и экспорта результатов.

Порядок роутов важен:
  /search     — строка, должна быть выше /{task_id}
  /export/docx — выше /export/{fmt}
"""
from __future__ import annotations

import logging
import mimetypes
import re
from pathlib import Path
from typing import Iterator

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse

from app.config import settings
from app.schemas.tasks import Task, TaskStatus
from app.services.audio_extractor import (
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    prepare_audio_for_transcription,
)
from app.services.exporters import DocxStyle, ExportFormat, export_docx, export_text
from app.services.task_store import task_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tasks", tags=["tasks"])

CHUNK_SIZE = 64 * 1024


@router.get(
    "",
    response_model=list[Task],
    summary="Список всех задач (от новых к старым)",
)
def list_tasks() -> list[Task]:
    return task_store.list_all()


# ВАЖНО: /search раньше /{task_id}, иначе "search" матчится на task_id.
@router.get(
    "/search",
    response_model=list[Task],
    summary="Полнотекстовый поиск по транскриптам (FTS5)",
)
def search_tasks(
    q: str = Query(..., description="Поисковый запрос (FTS5 синтаксис)"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Task]:
    """
    Ищет задачи, в сегментах которых есть совпадение с q.
    Поддерживает FTS5-синтаксис: "точная фраза", слово*, A OR B.
    """
    try:
        return task_store.search_by_text(q, limit=limit)
    except Exception as e:
        # FTS5 может бросить на невалидном синтаксисе (например, одиночная скобка).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Невалидный поисковый запрос: {e}",
        ) from e


@router.get(
    "/{task_id}",
    response_model=Task,
    summary="Получить задачу по ID",
)
def get_task(task_id: str) -> Task:
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Задача {task_id} не найдена",
        )
    return task


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить задачу из истории",
)
def delete_task(task_id: str) -> Response:
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Задача {task_id} не найдена",
        )
    task_store.delete(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _get_completed_task(task_id: str) -> Task:
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Задача {task_id} не найдена",
        )
    if task.status is not TaskStatus.COMPLETED or task.result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Задача ещё не завершена (статус: {task.status.value})",
        )
    return task


# ВАЖНО: /export/docx раньше /export/{fmt}.
@router.get(
    "/{task_id}/export/docx",
    summary="Скачать результат в DOCX с выбором стиля",
)
def export_task_docx(
    task_id: str,
    style: DocxStyle = Query(default=DocxStyle.TIMECODED),
) -> Response:
    task = _get_completed_task(task_id)
    content = export_docx(task.result, style, title=task.source_info)
    filename = f"{task_id}.{style.value}.docx"
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/{task_id}/export/{fmt}",
    summary="Скачать результат в txt / srt / vtt / json",
)
def export_task_text(task_id: str, fmt: ExportFormat) -> Response:
    task = _get_completed_task(task_id)
    content, media_type = export_text(task.result, fmt)
    filename = f"{task_id}.{fmt.value}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# -------------------- Audio streaming --------------------

@router.get(
    "/{task_id}/audio",
    summary="Получить аудиофайл задачи для воспроизведения в браузере",
)
def get_task_audio(task_id: str, request: Request) -> Response:
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Задача {task_id} не найдена",
        )

    source = _locate_source(task)
    if source is None or not source.exists():
        logger.warning("Audio: исходник не найден для task %s", task_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Исходный файл не найден",
        )

    try:
        audio_path = prepare_audio_for_transcription(source)
    except Exception as e:
        logger.exception("Audio: не удалось подготовить аудио для %s", task_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка подготовки аудио: {e}",
        ) from e

    if not audio_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Аудиофайл не создан",
        )

    return _stream_file_with_range(audio_path, request)


def _stream_file_with_range(path: Path, request: Request) -> Response:
    file_size = path.stat().st_size
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    range_header = request.headers.get("range") or request.headers.get("Range")

    if range_header is None:
        return StreamingResponse(
            _stream_full(path),
            status_code=status.HTTP_200_OK,
            media_type=media_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
            },
        )

    parsed = _parse_range_header(range_header, file_size)
    if parsed is None:
        return Response(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    start, end = parsed
    length = end - start + 1
    return StreamingResponse(
        _stream_range(path, start, length),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(length),
        },
    )


def _parse_range_header(header: str, file_size: int) -> tuple[int, int] | None:
    match = re.match(r"^bytes=(\d*)-(\d*)$", header.strip())
    if not match:
        return None
    start_str, end_str = match.group(1), match.group(2)
    if start_str == "" and end_str == "":
        return None
    if start_str == "":
        suffix = int(end_str)
        if suffix <= 0:
            return None
        start = max(0, file_size - suffix)
        end = file_size - 1
    else:
        start = int(start_str)
        end = int(end_str) if end_str else file_size - 1
    if start < 0 or end < start or start >= file_size:
        return None
    end = min(end, file_size - 1)
    return start, end


def _stream_full(path: Path) -> Iterator[bytes]:
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            yield chunk


def _stream_range(path: Path, start: int, length: int) -> Iterator[bytes]:
    with path.open("rb") as f:
        f.seek(start)
        remaining = length
        while remaining > 0:
            chunk = f.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _locate_source(task: Task) -> Path | None:
    allowed = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
    for candidate in settings.uploads_dir.glob(f"{task.task_id}.*"):
        if candidate.suffix.lower() in allowed:
            return candidate
    if task.local_source_path:
        return Path(task.local_source_path)
    return None
