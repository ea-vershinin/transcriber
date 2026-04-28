"""
Извлечение аудиодорожки из видеофайла через ffmpeg.

Зачем: видеофайлы курсов весят гигабайты, и 90% этого — видеопоток,
который нам не нужен. Звук того же урока занимает десятки МБ.
Плюс Whisper всё равно не может ничего с видео — ему нужен только звук.

Используем ffmpeg как внешнюю утилиту (системный путь). Вариант через
python-ffmpeg-обёртки быстрее не сделает — там та же утилита под капотом.
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


# Какие форматы считаем «аудио как есть» — извлекать ничего не нужно.
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".aac"}

# Какие форматы — видео, из них тянем звук.
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".webm", ".wmv", ".flv"}

# Что вообще поддерживаем.
SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


class AudioExtractionError(RuntimeError):
    """ffmpeg упал или файл не читается."""


def prepare_audio_for_transcription(source_path: Path) -> Path:
    """
    Возвращает путь к аудиофайлу, который можно скормить Whisper.

    - Если source — аудио (.mp3/.wav/etc.), просто возвращаем его.
    - Если source — видео (.mp4/.avi/etc.), извлекаем дорожку в m4a
      и кладём в storage/audio_cache/ под именем <хэш>.m4a.
      Хэш — от абсолютного пути и mtime, так что один и тот же файл
      не извлекается повторно.
    """
    source_path = source_path.resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Не найден: {source_path}")

    extension = source_path.suffix.lower()
    if extension in AUDIO_EXTENSIONS:
        return source_path

    if extension not in VIDEO_EXTENSIONS:
        raise AudioExtractionError(
            f"Неподдерживаемое расширение {extension}. "
            f"Разрешены: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    cache_dir = settings.project_root / "storage" / "audio_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Ключ кэша: путь + дата изменения. Переместили файл — извлечём заново.
    stat = source_path.stat()
    key_raw = f"{source_path}|{stat.st_mtime_ns}|{stat.st_size}"
    cache_key = hashlib.sha1(key_raw.encode("utf-8")).hexdigest()[:16]
    target = cache_dir / f"{cache_key}.m4a"

    if target.exists():
        logger.info("Аудио уже в кэше: %s", target.name)
        return target

    _extract_with_ffmpeg(source_path, target)
    return target


def _extract_with_ffmpeg(source: Path, target: Path) -> None:
    """Запускаем ffmpeg, копируя аудиопоток без перекодировки если возможно."""
    logger.info("ffmpeg: извлекаю звук из %s", source.name)

    # -vn              — убрать видео
    # -c:a aac         — кодек AAC (совместим с .m4a контейнером)
    # -b:a 128k        — битрейт 128 кбит/с (более чем достаточно для речи)
    # -ar 16000        — ресемплинг в 16 кГц (Whisper всё равно сэмплит так)
    # -ac 1            — моно (тоже Whisper-friendly, экономит место)
    # -y               — перезаписывать без вопросов
    # -hide_banner     — убрать шапку
    # -loglevel error  — только реальные ошибки в stderr
    cmd = [
        "ffmpeg",
        "-i", str(source),
        "-vn",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "16000",
        "-ac", "1",
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        str(target),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as e:
        raise AudioExtractionError(
            "ffmpeg не найден в PATH. Установите через "
            "`winget install ffmpeg` и перезапустите терминал."
        ) from e

    if result.returncode != 0:
        # Удалим файл-огрызок, если успел создаться
        target.unlink(missing_ok=True)
        raise AudioExtractionError(
            f"ffmpeg вернул код {result.returncode}: {result.stderr.strip()}"
        )

    size_mb = target.stat().st_size / 1024 / 1024
    logger.info("Звук извлечён: %s (%.1f МБ)", target.name, size_mb)
