import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { deleteTask, listTasks, searchTasks } from "../api";

const STATUS_FILTERS = [
  { id: "all", label: "Все" },
  { id: "processing", label: "В работе" },
  { id: "completed", label: "Готово" },
  { id: "failed", label: "Ошибка" },
];

/**
 * Список задач.
 *
 * Два режима поиска:
 *   - Фильтр по имени файла / URL — локально, в браузере (фильтрует tasks[]).
 *   - Полнотекстовый поиск по тексту транскриптов — через /api/tasks/search.
 *     Активируется при вводе в строку поиска чего-то похожего на фразу
 *     и нажатии Enter (или через debounce 500 мс).
 *
 * Упрощённый UI: одна строка поиска + переключатель "в именах / в тексте".
 */
export default function TasksList() {
  const [tasks, setTasks] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState("name"); // "name" | "text"
  const [fullTextResults, setFullTextResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);

  // Polling задач — только в режиме поиска по имени.
  useEffect(() => {
    if (searchMode === "text") return; // в режиме FTS не поллим
    let cancelled = false;

    async function fetchOnce() {
      try {
        const data = await listTasks();
        if (!cancelled) {
          setTasks(data);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
          setLoading(false);
        }
      }
    }

    fetchOnce();
    const intervalId = setInterval(fetchOnce, 2000);
    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [searchMode]);

  // FTS-поиск с debounce при вводе.
  useEffect(() => {
    if (searchMode !== "text") {
      setFullTextResults(null);
      setSearchError(null);
      return;
    }
    if (!query.trim()) {
      setFullTextResults([]);
      setSearchError(null);
      return;
    }

    let cancelled = false;
    setSearching(true);
    const timerId = setTimeout(async () => {
      try {
        const data = await searchTasks(query.trim());
        if (!cancelled) {
          setFullTextResults(data);
          setSearchError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setSearchError(err.message);
          setFullTextResults([]);
        }
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 500);

    return () => {
      cancelled = true;
      clearTimeout(timerId);
    };
  }, [query, searchMode]);

  // Локальная фильтрация — применяется только в режиме "name".
  const filtered = useMemo(() => {
    if (searchMode === "text") {
      return fullTextResults ?? [];
    }
    let list = tasks;
    if (filter !== "all") {
      if (filter === "processing") {
        list = list.filter(
          (t) => t.status === "processing" || t.status === "pending"
        );
      } else {
        list = list.filter((t) => t.status === filter);
      }
    }
    const q = query.trim().toLowerCase();
    if (q) {
      list = list.filter((t) => t.source_info.toLowerCase().includes(q));
    }
    return list;
  }, [tasks, filter, query, searchMode, fullTextResults]);

  async function handleDelete(taskId) {
    if (!confirm("Удалить задачу из истории? Исходные файлы не трогаем.")) {
      return;
    }
    try {
      await deleteTask(taskId);
      setTasks((prev) => prev.filter((t) => t.task_id !== taskId));
      if (fullTextResults) {
        setFullTextResults((prev) =>
          prev ? prev.filter((t) => t.task_id !== taskId) : prev
        );
      }
    } catch (err) {
      alert(`Не удалось удалить: ${err.message}`);
    }
  }

  return (
    <>
      <TasksToolbar
        filter={filter}
        setFilter={setFilter}
        query={query}
        setQuery={setQuery}
        searchMode={searchMode}
        setSearchMode={setSearchMode}
        totalCount={tasks.length}
        filteredCount={filtered.length}
        searching={searching}
      />

      {searchMode === "name" && loading && (
        <div className="muted">Загрузка списка задач…</div>
      )}
      {searchMode === "name" && error && (
        <div className="error">Ошибка: {error}</div>
      )}
      {searchMode === "text" && searchError && (
        <div className="error">Ошибка поиска: {searchError}</div>
      )}

      {!loading && !searching && filtered.length === 0 && (
        <div className="muted">
          {searchMode === "text" && query.trim()
            ? "Ничего не найдено в тексте транскриптов."
            : tasks.length === 0
            ? "Задач пока нет."
            : "Нет задач, подходящих под фильтр."}
        </div>
      )}

      <div className="tasks-list">
        {filtered.map((task) => (
          <TaskRow
            key={task.task_id}
            task={task}
            onDelete={() => handleDelete(task.task_id)}
          />
        ))}
      </div>
    </>
  );
}

function TasksToolbar({
  filter, setFilter, query, setQuery,
  searchMode, setSearchMode,
  totalCount, filteredCount, searching,
}) {
  return (
    <div className="tasks-toolbar">
      {searchMode === "name" && (
        <div className="status-filters">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`filter-chip ${filter === f.id ? "filter-chip-active" : ""}`}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
      )}

      <div className="search-group">
        <select
          className="search-mode"
          value={searchMode}
          onChange={(e) => setSearchMode(e.target.value)}
          title="Где искать"
        >
          <option value="name">по имени</option>
          <option value="text">по тексту</option>
        </select>
        <input
          type="search"
          className="search-input"
          placeholder={
            searchMode === "text"
              ? "Слово или фраза в транскриптах…"
              : "Имя файла или URL…"
          }
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <span className="muted count-badge">
        {searching ? "поиск…" : `${filteredCount}/${totalCount}`}
      </span>
    </div>
  );
}

function TaskRow({ task, onDelete }) {
  const badgeClass = `badge badge-${task.status}`;
  const created = new Date(task.created_at).toLocaleString("ru-RU");

  function handleDeleteClick(e) {
    e.preventDefault();
    e.stopPropagation();
    onDelete();
  }

  return (
    <div className="task-row-wrapper">
      <Link to={`/tasks/${task.task_id}`} className="task-row-link">
        <div className="task-row">
          <div className="task-main">
            <span className={badgeClass}>{statusLabel(task.status)}</span>
            <span className="task-source">{task.source_info}</span>
          </div>
          <div className="task-meta">
            <span className="muted">{sourceLabel(task.source)}</span>
            <span className="muted">{created}</span>
            {task.result && (
              <span className="muted">
                {Math.round(task.result.duration_sec)} сек. аудио
              </span>
            )}
          </div>
          {task.error && <div className="task-error">{task.error}</div>}
          {task.exported_files?.length > 0 && (
            <div className="task-exports">
              Сохранено: {task.exported_files.length} файл(ов)
            </div>
          )}
        </div>
      </Link>
      <button
        type="button"
        className="btn-icon-delete"
        onClick={handleDeleteClick}
        title="Удалить из истории"
      >
        ×
      </button>
    </div>
  );
}

function statusLabel(status) {
  return {
    pending: "в очереди",
    processing: "обрабатывается",
    completed: "готово",
    failed: "ошибка",
  }[status] ?? status;
}

function sourceLabel(source) {
  return {
    upload: "загрузка",
    youtube: "YouTube",
    local: "локальный файл",
  }[source] ?? source;
}
