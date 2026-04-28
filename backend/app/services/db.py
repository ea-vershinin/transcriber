"""
SQLite-хранилище для задач и сегментов.

Используем встроенный модуль sqlite3. Одна база на всё приложение.

Особенности:
  - PRAGMA foreign_keys=ON — без этого FK не работают в SQLite.
  - PRAGMA journal_mode=WAL — безопаснее для конкурентных запросов.
  - FTS5-таблица segments_fts автоматически синхронизируется
    через триггеры.
  - Схема версионируется через PRAGMA user_version.

Threading: в Python sqlite3 по умолчанию запрещает делить connection
между потоками. Мы создаём отдельный connection на поток через
threading.local() — это правильный подход для FastAPI с BackgroundTasks.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.config import settings

logger = logging.getLogger(__name__)


# Где лежит файл БД.
DB_PATH: Path = settings.project_root / "storage" / "transcriber.db"

# Текущая версия схемы. Если в будущем меняем структуру, увеличиваем
# число и добавляем новую миграцию.
SCHEMA_VERSION = 1


# Отдельный connection на поток — безопасно для многопоточной среды.
_local = threading.local()


def _connect() -> sqlite3.Connection:
    """Создаёт новое соединение с SQLite и настраивает его."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(DB_PATH),
        # detect_types позволяет автоматически преобразовывать DATETIME и т.п.,
        # но мы храним как TEXT (ISO), так что оставляем по умолчанию.
        check_same_thread=False,  # threading.local даёт свой conn на поток
    )
    # Row factory: результаты возвращаются как dict-подобные объекты.
    conn.row_factory = sqlite3.Row
    # Включаем FK (в SQLite по умолчанию выключены — исторически).
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL-режим — лучше для параллельных чтений во время записи.
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_conn() -> sqlite3.Connection:
    """Возвращает connection текущего потока, создавая при необходимости."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
    return conn


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    """
    Транзакция: commit при успехе, rollback при исключении.

    Использование:
        with tx() as conn:
            conn.execute("INSERT ...")
            conn.execute("UPDATE ...")
    """
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# -------------------- Миграции --------------------

def init_db() -> None:
    """Создаёт таблицы, если их нет. Применяет миграции до SCHEMA_VERSION."""
    conn = get_conn()
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]

    if current_version == 0:
        logger.info("Инициализация БД (версия 0 → %d)", SCHEMA_VERSION)
        with tx() as c:
            _apply_migration_v1(c)
            c.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        logger.info("БД готова: %s", DB_PATH)
    elif current_version < SCHEMA_VERSION:
        logger.info("Миграция БД: %d → %d", current_version, SCHEMA_VERSION)
        # Место для будущих миграций (v2, v3...).
        # Пример:
        #   if current_version < 2:
        #       _apply_migration_v2(c)
        raise NotImplementedError(
            f"Миграция с версии {current_version} пока не реализована"
        )
    elif current_version > SCHEMA_VERSION:
        raise RuntimeError(
            f"БД версии {current_version}, а код рассчитан на {SCHEMA_VERSION}. "
            "Откатитесь на более новую версию приложения."
        )
    # current_version == SCHEMA_VERSION — ничего не делаем, всё ок.


def _apply_migration_v1(conn: sqlite3.Connection) -> None:
    """Начальная схема: tasks, segments, exported_files, FTS-индекс."""

    # Основная таблица задач.
    conn.execute("""
        CREATE TABLE tasks (
            task_id           TEXT PRIMARY KEY,
            status            TEXT NOT NULL,
            source            TEXT NOT NULL,
            source_info       TEXT NOT NULL,
            local_source_path TEXT,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL,
            error             TEXT,
            -- результат (плоско):
            language          TEXT,
            duration_sec      REAL,
            processing_sec    REAL,
            translated        INTEGER NOT NULL DEFAULT 0,
            model_used        TEXT
        )
    """)
    conn.execute("CREATE INDEX idx_tasks_created_at ON tasks(created_at DESC)")
    conn.execute("CREATE INDEX idx_tasks_status ON tasks(status)")
    # Для дедупликации: быстрый поиск завершённых задач по local_source_path.
    conn.execute("""
        CREATE INDEX idx_tasks_local_source_path
        ON tasks(local_source_path)
        WHERE local_source_path IS NOT NULL
    """)

    # Сегменты транскрипта.
    conn.execute("""
        CREATE TABLE segments (
            task_id   TEXT NOT NULL,
            idx       INTEGER NOT NULL,
            start_sec REAL NOT NULL,
            end_sec   REAL NOT NULL,
            text      TEXT NOT NULL,
            speaker   TEXT,
            PRIMARY KEY (task_id, idx),
            FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
        )
    """)

    # Файлы, сохранённые рядом с исходником.
    conn.execute("""
        CREATE TABLE exported_files (
            task_id TEXT NOT NULL,
            path    TEXT NOT NULL,
            PRIMARY KEY (task_id, path),
            FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
        )
    """)

    # FTS5 индекс по тексту сегментов. Используем "external content":
    # сам текст остаётся в segments.text, FTS-таблица хранит только индекс.
    # Экономит место и избавляет от дублирования данных.
    conn.execute("""
        CREATE VIRTUAL TABLE segments_fts USING fts5(
            text,
            task_id UNINDEXED,
            content='segments',
            content_rowid='rowid',
            tokenize='unicode61'
        )
    """)

    # Триггеры для автоматической синхронизации FTS с segments.
    # Без них после INSERT/UPDATE/DELETE поиск не найдёт новые данные.
    conn.execute("""
        CREATE TRIGGER segments_ai AFTER INSERT ON segments BEGIN
            INSERT INTO segments_fts(rowid, text, task_id)
            VALUES (new.rowid, new.text, new.task_id);
        END
    """)
    conn.execute("""
        CREATE TRIGGER segments_ad AFTER DELETE ON segments BEGIN
            INSERT INTO segments_fts(segments_fts, rowid, text, task_id)
            VALUES ('delete', old.rowid, old.text, old.task_id);
        END
    """)
    conn.execute("""
        CREATE TRIGGER segments_au AFTER UPDATE ON segments BEGIN
            INSERT INTO segments_fts(segments_fts, rowid, text, task_id)
            VALUES ('delete', old.rowid, old.text, old.task_id);
            INSERT INTO segments_fts(rowid, text, task_id)
            VALUES (new.rowid, new.text, new.task_id);
        END
    """)
