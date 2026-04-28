"""
Асинхронные эндпоинты транскрибации.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field, HttpUrl

from app.config import settings
from app.schemas.tasks import (
    AutoExportFormat,
    BatchCreated,
    TaskCreated,
    TaskSource,
    TaskStatus,
)
from app.schemas.transcription import TranscriptionOptions
from app.services.audio_extractor import (
    SUPPORTED_EXTENSIONS,
    AudioExtractionError,
    prepare_audio_for_transcription,
)
from app.services.exporters import DocxStyle, ExportFormat, export_docx, export_text
from app.services.folder_scanner import scan_folder
from app.services.task_store import task_store
from app.services.youtube import YouTubeDownloadError, download_audio
from app.transcriber import transcriber

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/transcribe", tags=["transcription"])


# ---------- Вспомогательные функции ----------

def _validate_extension(file: UploadFile) -> str:
    original_name = Path(file.filename or "audio").name
    extension = Path(original_name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неподдерживаемый формат: {extension}. "
                   f"Разрешены: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )
    return extension


def _save_upload_as(file: UploadFile, task_id: str, extension: str) -> Path:
    target_path = settings.uploads_dir / f"{task_id}{extension}"
    max_bytes = settings.max_upload_mb * 1024 * 1024
    total_bytes = 0

    with target_path.open("wb") as f:
        while chunk := file.file.read(1024 * 1024):
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                target_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Файл превышает лимит {settings.max_upload_mb} МБ",
                )
            f.write(chunk)

    logger.info("Файл сохранён: %s (%.1f МБ)",
                target_path.name, total_bytes / 1024 / 1024)
    return target_path


def _parse_options(raw: str | None) -> TranscriptionOptions:
    if not raw:
        return TranscriptionOptions()
    try:
        data = json.loads(raw)
        return TranscriptionOptions.model_validate(data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Невалидный JSON в поле options: {e}",
        ) from e


def _save_exports_beside_source(
    task_id: str,
    source_file: Path,
    result,
    formats: list[AutoExportFormat],
) -> None:
    base = source_file.with_suffix("")
    for fmt in formats:
        target: Path | None = None
        try:
            if fmt in (
                AutoExportFormat.TXT, AutoExportFormat.SRT,
                AutoExportFormat.VTT, AutoExportFormat.JSON,
            ):
                text_fmt = ExportFormat(fmt.value)
                content, _ = export_text(result, text_fmt)
                target = base.with_suffix(f".{fmt.value}")
                target.write_text(content, encoding="utf-8")
            elif fmt in (
                AutoExportFormat.DOCX_PLAIN,
                AutoExportFormat.DOCX_TIMECODED,
                AutoExportFormat.DOCX_FULL,
            ):
                style = DocxStyle(fmt.value.removeprefix("docx_"))
                suffix_map = {
                    DocxStyle.PLAIN: ".docx",
                    DocxStyle.TIMECODED: ".timecoded.docx",
                    DocxStyle.FULL: ".full.docx",
                }
                docx_bytes = export_docx(result, style, title=source_file.name)
                target = base.with_suffix("").parent / (
                    source_file.stem + suffix_map[style]
                )
                target.write_bytes(docx_bytes)

            if target:
                logger.info("Сохранено рядом: %s", target)
                task_store.add_exported_file(task_id, str(target))
        except Exception:
            logger.exception("Не удалось сохранить %s", fmt)


def _run_transcription(
    task_id: str,
    audio_path: Path,
    options: TranscriptionOptions,
) -> None:
    logger.info("[%s] Старт: %s", task_id, audio_path.name)
    task_store.mark_processing(task_id)
    try:
        result = transcriber.transcribe(audio_path, options=options)
        task_store.mark_completed(task_id, result)
        logger.info("[%s] Успех.", task_id)
    except Exception as e:
        logger.exception("[%s] Ошибка транскрибации", task_id)
        task_store.mark_failed(task_id, str(e))


def _run_youtube_pipeline(
    task_id: str,
    url: str,
    options: TranscriptionOptions,
) -> None:
    logger.info("[%s] YouTube pipeline: %s", task_id, url)
    task_store.mark_processing(task_id)
    try:
        audio_path = download_audio(
            url, output_dir=settings.uploads_dir, filename_stem=task_id,
        )
    except YouTubeDownloadError as e:
        task_store.mark_failed(task_id, f"Ошибка скачивания: {e}")
        return

    try:
        result = transcriber.transcribe(audio_path, options=options)
        task_store.mark_completed(task_id, result)
    except Exception as e:
        logger.exception("[%s] Ошибка транскрибации", task_id)
        task_store.mark_failed(task_id, f"Ошибка транскрибации: {e}")


def _run_local_pipeline(
    task_id: str,
    source_file: Path,
    options: TranscriptionOptions,
    auto_export: list[AutoExportFormat],
) -> None:
    logger.info("[%s] LOCAL pipeline: %s", task_id, source_file)
    task_store.mark_processing(task_id)

    try:
        audio_path = prepare_audio_for_transcription(source_file)
    except (FileNotFoundError, AudioExtractionError) as e:
        task_store.mark_failed(task_id, f"Извлечение аудио: {e}")
        return

    try:
        result = transcriber.transcribe(audio_path, options=options)
        task_store.mark_completed(task_id, result)
    except Exception as e:
        logger.exception("[%s] Ошибка транскрибации", task_id)
        task_store.mark_failed(task_id, f"Транскрибация: {e}")
        return

    if auto_export:
        _save_exports_beside_source(task_id, source_file, result, auto_export)


# ---------- Схемы запросов ----------

class LocalFileRequest(BaseModel):
    path: str = Field(..., description="Абсолютный путь к файлу на диске сервера")
    options: TranscriptionOptions = TranscriptionOptions()
    auto_export: list[AutoExportFormat] = Field(
        default_factory=lambda: [AutoExportFormat.DOCX_TIMECODED],
    )
    force: bool = Field(
        default=False,
        description="Обработать заново, даже если файл уже есть в БД.",
    )


class FolderRequest(BaseModel):
    path: str = Field(..., description="Абсолютный путь к папке на диске сервера")
    recursive: bool = Field(default=True)
    options: TranscriptionOptions = TranscriptionOptions()
    auto_export: list[AutoExportFormat] = Field(
        default_factory=lambda: [AutoExportFormat.DOCX_TIMECODED],
    )
    force: bool = Field(
        default=False,
        description="Обработать заново даже те файлы, что уже есть в БД.",
    )


class YouTubeRequest(BaseModel):
    url: HttpUrl
    options: TranscriptionOptions = TranscriptionOptions()


class BatchCreatedWithSkipped(BatchCreated):
    """Ответ батч-эндпоинта: дополнительно — сколько пропущено."""
    skipped: int = 0


# ---------- Эндпоинты ----------

@router.post(
    "/file",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Загрузить файл (аудио или видео) и запустить транскрибацию",
)
def transcribe_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    options: str | None = Form(default=None),
) -> TaskCreated:
    opts = _parse_options(options)
    extension = _validate_extension(file)

    task = task_store.create(
        source=TaskSource.UPLOAD,
        source_info=file.filename or f"upload{extension}",
    )

    try:
        saved_path = _save_upload_as(file, task.task_id, extension)
    except Exception:
        task_store.delete(task.task_id)
        raise

    def _worker() -> None:
        try:
            audio_path = prepare_audio_for_transcription(saved_path)
        except Exception as e:
            task_store.mark_failed(task.task_id, f"Подготовка аудио: {e}")
            return
        _run_transcription(task.task_id, audio_path, opts)

    background_tasks.add_task(_worker)
    return TaskCreated(task_id=task.task_id, status=task.status)


@router.post(
    "/youtube",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
def transcribe_youtube(
    payload: YouTubeRequest,
    background_tasks: BackgroundTasks,
) -> TaskCreated:
    task = task_store.create(
        source=TaskSource.YOUTUBE,
        source_info=str(payload.url),
    )
    background_tasks.add_task(
        _run_youtube_pipeline, task.task_id, str(payload.url), payload.options,
    )
    return TaskCreated(task_id=task.task_id, status=task.status)


@router.post(
    "/local",
    response_model=TaskCreated,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Обработать один локальный файл",
)
def transcribe_local_file(
    payload: LocalFileRequest,
    background_tasks: BackgroundTasks,
) -> TaskCreated:
    path = Path(payload.path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Файл не найден: {payload.path}",
        )
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Это не файл: {payload.path}",
        )
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неподдерживаемое расширение: {path.suffix}",
        )

    # Дедупликация: если не force и уже есть completed-задача для этого файла,
    # возвращаем её.
    abs_path = str(path.resolve())
    if not payload.force:
        existing = task_store.find_completed_by_local_path(abs_path)
        if existing is not None:
            logger.info(
                "Dedup: файл %s уже обработан в task %s — возвращаем существующую",
                path.name, existing.task_id,
            )
            return TaskCreated(task_id=existing.task_id, status=existing.status)

    task = task_store.create(
        source=TaskSource.LOCAL,
        source_info=path.name,
        local_source_path=abs_path,
    )
    background_tasks.add_task(
        _run_local_pipeline, task.task_id, path, payload.options, payload.auto_export,
    )
    return TaskCreated(task_id=task.task_id, status=task.status)


@router.post(
    "/folder",
    response_model=BatchCreatedWithSkipped,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Обработать все медиафайлы в папке (батч)",
)
def transcribe_folder(
    payload: FolderRequest,
    background_tasks: BackgroundTasks,
) -> BatchCreatedWithSkipped:
    folder = Path(payload.path)
    try:
        files = scan_folder(folder, recursive=payload.recursive)
    except (FileNotFoundError, NotADirectoryError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e),
        ) from e

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"В папке нет поддерживаемых файлов "
                   f"({', '.join(sorted(SUPPORTED_EXTENSIONS))})",
        )

    task_ids: list[str] = []
    skipped = 0
    for file_path in files:
        abs_path = str(file_path.resolve())

        # Дедупликация по файлу — если не force.
        if not payload.force:
            existing = task_store.find_completed_by_local_path(abs_path)
            if existing is not None:
                skipped += 1
                continue

        task = task_store.create(
            source=TaskSource.LOCAL,
            source_info=file_path.name,
            local_source_path=abs_path,
        )
        background_tasks.add_task(
            _run_local_pipeline,
            task.task_id, file_path, payload.options, payload.auto_export,
        )
        task_ids.append(task.task_id)

    logger.info(
        "Batch: запущено %d задач, пропущено %d (уже обработаны) для %s",
        len(task_ids), skipped, folder,
    )
    return BatchCreatedWithSkipped(
        task_ids=task_ids,
        files_found=len(files),
        skipped=skipped,
    )
