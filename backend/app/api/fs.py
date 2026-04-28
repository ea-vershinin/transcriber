"""
Эндпоинты для просмотра файловой системы сервера.

ВАЖНО про безопасность: мы намеренно даём браузеру возможность видеть диск,
потому что сервер запущен на локальной машине пользователя. Если вы
когда-нибудь захотите вынести этот бэкенд наружу — эти эндпоинты нужно
либо выключить, либо жёстко ограничить доступом.
"""
from __future__ import annotations

import os
import string
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

router = APIRouter(prefix="/api/fs", tags=["filesystem"])


class FsEntry(BaseModel):
    name: str
    path: str            # абсолютный путь
    is_dir: bool


class FsListing(BaseModel):
    path: str                    # текущая папка (абсолютный путь)
    parent: str | None           # родительская папка, или None если корень
    entries: list[FsEntry]       # содержимое
    drives: list[str]            # список дисков (только на Windows, иначе [])


@router.get(
    "/browse",
    response_model=FsListing,
    summary="Получить содержимое папки (для выбора пути)",
)
def browse(
    path: str = Query(
        default="",
        description="Путь к папке. Пустая строка — корень (Windows: список дисков).",
    ),
) -> FsListing:
    """
    Возвращает список папок и файлов в указанной папке.

    Чтобы на фронте строить хлебные крошки и кнопку "назад", возвращаем
    также parent. На Windows при пустом path возвращаем список дисков.
    """
    # Корневой случай на Windows — вернём список дисков.
    if not path:
        drives = _list_windows_drives()
        if drives:
            return FsListing(
                path="",
                parent=None,
                entries=[
                    FsEntry(name=drive, path=drive, is_dir=True)
                    for drive in drives
                ],
                drives=drives,
            )
        # Linux/Mac — показываем "/"
        path = "/"

    p = Path(path)
    if not p.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Путь не найден: {path}",
        )
    if not p.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Это не папка: {path}",
        )

    # Определяем parent
    parent = _get_parent(p)

    entries: list[FsEntry] = []
    try:
        for item in p.iterdir():
            # Пропускаем скрытые файлы (начинающиеся с точки).
            # На Windows тоже пропустим системные/скрытые, чтобы не засорять.
            if item.name.startswith("."):
                continue
            try:
                is_dir = item.is_dir()
            except PermissionError:
                # Некоторые системные папки недоступны для is_dir — пропускаем.
                continue
            entries.append(
                FsEntry(name=item.name, path=str(item.resolve()), is_dir=is_dir)
            )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Нет прав на чтение папки: {e}",
        ) from e

    # Сортировка: сначала папки, потом файлы; каждую группу по алфавиту.
    entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))

    return FsListing(
        path=str(p.resolve()),
        parent=parent,
        entries=entries,
        drives=_list_windows_drives(),
    )


def _list_windows_drives() -> list[str]:
    """Список существующих дисков на Windows. На других ОС — пустой список."""
    if os.name != "nt":
        return []
    drives = []
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if Path(drive).exists():
            drives.append(drive)
    return drives


def _get_parent(p: Path) -> str | None:
    """Родительская папка. На корне диска (C:\\) — None; на "/" — None."""
    resolved = p.resolve()
    parent = resolved.parent
    # Для "C:\" resolved == parent (путь сам себе родитель) → вернём None.
    if parent == resolved:
        return None
    return str(parent)
