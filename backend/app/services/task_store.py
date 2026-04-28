"""
Хранилище задач на SQLite.

Публичный интерфейс совпадает с предыдущей in-memory версией, плюс
добавлены find_completed_by_local_path (для дедупликации) и search_by_text
(полнотекстовый поиск через FTS5).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from app.schemas.tasks import Task, TaskSource, TaskStatus
from app.schemas.transcription import Segment, TranscriptionResult
from app.services.db import get_conn, tx

logger = logging.getLogger(__name__)


class TaskStore:
    # ---------- Создание / чтение ----------

    def create(
        self,
        source: TaskSource,
        source_info: str,
        local_source_path: str | None = None,
    ) -> Task:
        task_id = uuid.uuid4().hex
        now = datetime.now()
        task = Task(
            task_id=task_id,
            status=TaskStatus.PENDING,
            source=source,
            source_info=source_info,
            created_at=now,
            updated_at=now,
            local_source_path=local_source_path,
        )
        with tx() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, status, source, source_info, local_source_path,
                    created_at, updated_at, translated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    task.task_id,
                    task.status.value,
                    task.source.value,
                    task.source_info,
                    task.local_source_path,
                    task.created_at.isoformat(),
                    task.updated_at.isoformat(),
                ),
            )
        return task

    def get(self, task_id: str) -> Task | None:
        conn = get_conn()
        row = conn.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_task(conn, row)

    def list_all(self) -> list[Task]:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_task(conn, row) for row in rows]

    def find_completed_by_local_path(self, path: str) -> Task | None:
        """
        Для дедупликации: ищет последнюю COMPLETED-задачу с таким local_source_path.

        Если найдена — новая задача не нужна, можно вернуть эту.
        """
        conn = get_conn()
        row = conn.execute(
            """
            SELECT * FROM tasks
            WHERE local_source_path = ? AND status = 'completed'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (path,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_task(conn, row)

    def search_by_text(self, query: str, limit: int = 50) -> list[Task]:
        """
        Полнотекстовый поиск по распознанному тексту через FTS5.

        Возвращает задачи, в сегментах которых найдено совпадение.
        Каждая задача — один раз, даже если совпадений несколько.
        """
        if not query.strip():
            return []
        conn = get_conn()
        # Используем GROUP BY по task_id, чтобы не дублировать задачи.
        # ORDER BY created_at — новые первыми.
        rows = conn.execute(
            """
            SELECT DISTINCT t.*
            FROM tasks t
            INNER JOIN segments_fts fts ON fts.task_id = t.task_id
            WHERE segments_fts MATCH ?
            ORDER BY t.created_at DESC
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
        return [self._row_to_task(conn, row) for row in rows]

    # ---------- Обновление статусов ----------

    def mark_processing(self, task_id: str) -> None:
        self._update_status(task_id, TaskStatus.PROCESSING)

    def mark_failed(self, task_id: str, error: str) -> None:
        with tx() as conn:
            conn.execute(
                "UPDATE tasks SET status=?, error=?, updated_at=? WHERE task_id=?",
                (TaskStatus.FAILED.value, error, datetime.now().isoformat(), task_id),
            )

    def mark_completed(self, task_id: str, result: TranscriptionResult) -> None:
        """Помечаем задачу завершённой + сохраняем сегменты + метаданные."""
        now = datetime.now().isoformat()
        with tx() as conn:
            conn.execute(
                """
                UPDATE tasks SET
                    status=?, updated_at=?, error=NULL,
                    language=?, duration_sec=?, processing_sec=?,
                    translated=?, model_used=?
                WHERE task_id=?
                """,
                (
                    TaskStatus.COMPLETED.value, now,
                    result.language, result.duration_sec, result.processing_sec,
                    1 if result.translated else 0, result.model_used,
                    task_id,
                ),
            )
            # Сегменты — на всякий случай удаляем старые и вставляем новые,
            # чтобы идемпотентно работало при повторной обработке.
            conn.execute("DELETE FROM segments WHERE task_id=?", (task_id,))
            conn.executemany(
                """
                INSERT INTO segments (task_id, idx, start_sec, end_sec, text, speaker)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (task_id, i, seg.start, seg.end, seg.text, seg.speaker)
                    for i, seg in enumerate(result.segments)
                ],
            )

    # ---------- Экспорты ----------

    def add_exported_file(self, task_id: str, file_path: str) -> None:
        with tx() as conn:
            # INSERT OR IGNORE — на случай повторного сохранения того же файла.
            conn.execute(
                "INSERT OR IGNORE INTO exported_files (task_id, path) VALUES (?, ?)",
                (task_id, file_path),
            )
            conn.execute(
                "UPDATE tasks SET updated_at=? WHERE task_id=?",
                (datetime.now().isoformat(), task_id),
            )

    # ---------- Удаление ----------

    def delete(self, task_id: str) -> bool:
        """Удаляет задачу. FK-каскад уберёт segments и exported_files."""
        with tx() as conn:
            cursor = conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
            return cursor.rowcount > 0

    # ---------- Внутренние helpers ----------

    def _update_status(self, task_id: str, status: TaskStatus) -> None:
        with tx() as conn:
            conn.execute(
                "UPDATE tasks SET status=?, updated_at=? WHERE task_id=?",
                (status.value, datetime.now().isoformat(), task_id),
            )

    def _row_to_task(self, conn, row) -> Task:
        """Собирает Task из строки БД + подгружает segments и exported_files."""
        task_id = row["task_id"]
        # Сегменты (если есть)
        seg_rows = conn.execute(
            """
            SELECT start_sec, end_sec, text, speaker
            FROM segments WHERE task_id=?
            ORDER BY idx
            """,
            (task_id,),
        ).fetchall()
        # Файлы экспорта
        export_rows = conn.execute(
            "SELECT path FROM exported_files WHERE task_id=?",
            (task_id,),
        ).fetchall()

        result: TranscriptionResult | None = None
        # Если есть duration_sec — задача завершена с результатом
        if row["duration_sec"] is not None and seg_rows:
            result = TranscriptionResult(
                language=row["language"] or "unknown",
                duration_sec=row["duration_sec"],
                processing_sec=row["processing_sec"] or 0.0,
                segments=[
                    Segment(
                        start=r["start_sec"],
                        end=r["end_sec"],
                        text=r["text"],
                        speaker=r["speaker"],
                    )
                    for r in seg_rows
                ],
                translated=bool(row["translated"]),
                model_used=row["model_used"],
            )

        return Task(
            task_id=task_id,
            status=TaskStatus(row["status"]),
            source=TaskSource(row["source"]),
            source_info=row["source_info"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            result=result,
            error=row["error"],
            local_source_path=row["local_source_path"],
            exported_files=[r["path"] for r in export_rows],
        )


task_store = TaskStore()
