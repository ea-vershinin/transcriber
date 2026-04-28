"""
Обработка папки с видео/аудио файлами.

Находит все поддерживаемые файлы в папке и создаёт по задаче на каждый.
Задачи обрабатываются последовательно (одна модель Whisper в памяти).
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.services.audio_extractor import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)


def scan_folder(folder_path: Path, recursive: bool = True) -> list[Path]:
    """
    Находит все поддерживаемые медиафайлы в папке.

    Args:
        folder_path: абсолютный или относительный путь к папке
        recursive: искать во вложенных папках (True) или только в корне (False)

    Returns:
        Отсортированный список путей. Пустой список — ничего не нашли.

    Raises:
        FileNotFoundError, NotADirectoryError при проблемах с путём.
    """
    folder_path = folder_path.resolve()
    if not folder_path.exists():
        raise FileNotFoundError(f"Папка не найдена: {folder_path}")
    if not folder_path.is_dir():
        raise NotADirectoryError(f"Это не папка: {folder_path}")

    pattern = "**/*" if recursive else "*"
    files: list[Path] = []
    for path in folder_path.glob(pattern):
        if not path.is_file():
            continue
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)

    files.sort()
    logger.info(
        "Сканирование %s: найдено %d файлов (recursive=%s)",
        folder_path, len(files), recursive,
    )
    return files
