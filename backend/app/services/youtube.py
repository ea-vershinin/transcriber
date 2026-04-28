"""
Скачивание аудиодорожки с YouTube (и 1000+ других сайтов) через yt-dlp.

Стратегия выбора формата:
  1. Пробуем "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio" — чистый аудиопоток.
  2. Если не вышло — берём "best" (видео+аудио) и потом вытащим звук ffmpeg-ом.

yt-dlp ломается периодически: YouTube меняет внутренности, а мы — версию либы.
Если что-то пошло не так, начните с апдейта:
    pip install --upgrade yt-dlp
"""
from __future__ import annotations

import logging
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

logger = logging.getLogger(__name__)


class YouTubeDownloadError(Exception):
    """Обёртка над ошибками yt-dlp, чтобы наверх не тянуть их напрямую."""


# Цепочка fallback-ов: yt-dlp сам пройдётся по вариантам, пока не найдёт
# рабочий. Слэш "/" означает "или следующий, если не вышло".
_FORMAT_CHAIN = (
    "bestaudio[ext=m4a]/"
    "bestaudio[ext=webm]/"
    "bestaudio/"
    "best[ext=mp4]/"
    "best"
)


def download_audio(url: str, output_dir: Path, filename_stem: str) -> Path:
    """
    Скачивает аудиодорожку ролика в output_dir под именем filename_stem.

    Args:
        url: ссылка на видео (YouTube, Vimeo, SoundCloud и т.д.)
        output_dir: папка для сохранения.
        filename_stem: имя файла без расширения — yt-dlp подставит своё.

    Returns:
        Путь к скачанному файлу. В большинстве случаев это будет .m4a или .webm;
        иногда .mp4 (если был взят видеопоток со звуком).

    Raises:
        YouTubeDownloadError: если скачать так и не получилось.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    # %(ext)s подставит реальное расширение скачанного файла.
    output_template = str(output_dir / f"{filename_stem}.%(ext)s")

    ydl_opts = {
        "format": _FORMAT_CHAIN,
        "outtmpl": output_template,
        "noplaylist": True,
        "writethumbnail": False,
        "quiet": True,
        "no_warnings": True,
        # Помогает с некоторыми сайтами, требующими HTTPS.
        "nocheckcertificate": False,
        # Retry при временных сетевых сбоях.
        "retries": 3,
    }

    logger.info("yt-dlp: качаем %s", url)
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_path = Path(ydl.prepare_filename(info))
    except DownloadError as e:
        # DownloadError — основной тип ошибок yt-dlp. Распаковываем красиво.
        logger.error("yt-dlp DownloadError для %s: %s", url, e)
        raise YouTubeDownloadError(_clean_error(str(e))) from e
    except Exception as e:
        logger.exception("Непредвиденная ошибка yt-dlp")
        raise YouTubeDownloadError(_clean_error(str(e))) from e

    if not downloaded_path.exists():
        raise YouTubeDownloadError(
            f"yt-dlp сработал без ошибок, но файл не найден: {downloaded_path}"
        )

    size_mb = downloaded_path.stat().st_size / 1024 / 1024
    logger.info("Скачано: %s (%.1f МБ)", downloaded_path.name, size_mb)
    return downloaded_path


def _clean_error(text: str) -> str:
    """
    Убираем ANSI-цветовые коды из сообщения об ошибке — они засоряют
    JSON-ответ API непечатаемыми символами вроде \\u001b[0;31m.
    """
    import re
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text).strip()
