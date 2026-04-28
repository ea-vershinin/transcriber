import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getAudioUrl, getTask } from "../api";

/**
 * Страница отдельной задачи с плеером и синхронизированным текстом.
 *
 * Важный момент про seek: ref привязан напрямую к <audio>,
 * никаких forwardRef / локального state в плеере. Так мы гарантированно
 * управляем именно тем DOM-элементом, который сейчас на экране.
 */
export default function TaskPage() {
  const { taskId } = useParams();
  const [task, setTask] = useState(null);
  const [error, setError] = useState(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [audioUnavailable, setAudioUnavailable] = useState(false);
  const audioRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    let intervalId = null;

    async function fetchOnce() {
      try {
        const data = await getTask(taskId);
        if (cancelled) return;
        setTask(data);
        setError(null);
        if (data.status === "completed" || data.status === "failed") {
          if (intervalId) clearInterval(intervalId);
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    }

    fetchOnce();
    intervalId = setInterval(fetchOnce, 2000);
    return () => {
      cancelled = true;
      if (intervalId) clearInterval(intervalId);
    };
  }, [taskId]);

  function handleTimeUpdate() {
    const audio = audioRef.current;
    if (audio) setCurrentTime(audio.currentTime);
  }

  /**
   * Переход к указанной секунде + старт воспроизведения.
   *
   * Нюансы:
   *   - play() возвращает Promise; если вызвать сразу после currentTime=,
   *     иногда браузер успевает сначала playback, и позиция сбивается.
   *     Поэтому сначала пауза → seek → play.
   *   - Если трек ещё не дошёл до состояния "can play" (readyState < 2),
   *     дожидаемся события loadedmetadata.
   */
  function seekTo(seconds) {
    const audio = audioRef.current;
    if (!audio) return;

    const applySeek = () => {
      audio.pause();
      audio.currentTime = seconds;
      audio.play().catch(() => {
        // Autoplay может быть заблокирован — пользователь просто нажмёт play.
      });
    };

    if (audio.readyState >= 1) {
      // Метаданные уже загружены — можем устанавливать currentTime
      applySeek();
    } else {
      // Трек ещё не готов — ждём события loadedmetadata
      audio.addEventListener("loadedmetadata", applySeek, { once: true });
      // И подтолкнём загрузку, если она не началась
      audio.load();
    }
  }  

  if (error) {
    return (
      <div className="section">
        <Link to="/" className="back-link">← К списку задач</Link>
        <div className="error">Ошибка: {error}</div>
      </div>
    );
  }
  if (!task) {
    return (
      <div className="section">
        <Link to="/" className="back-link">← К списку задач</Link>
        <div className="muted">Загрузка…</div>
      </div>
    );
  }

  return (
    <div className="section">
      <Link to="/" className="back-link">← К списку задач</Link>

      <div className="task-header">
        <h2 title={task.source_info}>{task.source_info}</h2>
        <span className={`badge badge-${task.status}`}>
          {statusLabel(task.status)}
        </span>
      </div>

      <TaskMeta task={task} />

      {task.status === "failed" && (
        <div className="message message-error">
          <strong>Не удалось обработать:</strong>
          <div className="task-error-text">{task.error}</div>
        </div>
      )}

      {task.status === "completed" && task.result && (
        <>
          <div className="audio-player">
            {!audioUnavailable ? (
              <audio
                ref={audioRef}
                controls
                preload="metadata"
                src={getAudioUrl(task.task_id)}
                onTimeUpdate={handleTimeUpdate}
                onError={() => setAudioUnavailable(true)}
              >
                Ваш браузер не поддерживает audio.
              </audio>
            ) : (
              <div className="muted">
                Аудиофайл недоступен (возможно, исходник перемещён или удалён).
              </div>
            )}
          </div>

          <ExportButtons taskId={task.task_id} />
          <SegmentsView
            segments={task.result.segments}
            currentTime={currentTime}
            onSeek={seekTo}
          />
        </>
      )}

      {(task.status === "pending" || task.status === "processing") && (
        <div className="muted" style={{ marginTop: "1rem" }}>
          Страница обновляется автоматически каждые 2 сек.
        </div>
      )}
    </div>
  );
}

function TaskMeta({ task }) {
  const created = new Date(task.created_at).toLocaleString("ru-RU");
  const updated = new Date(task.updated_at).toLocaleString("ru-RU");
  const result = task.result;

  return (
    <div className="task-meta-box">
      <MetaRow label="Источник" value={sourceLabel(task.source)} />
      <MetaRow label="Создана" value={created} />
      {task.status !== "pending" && (
        <MetaRow label="Обновлена" value={updated} />
      )}
      {task.local_source_path && (
        <MetaRow label="Путь" value={task.local_source_path} mono />
      )}
      {result && (
        <>
          <MetaRow label="Язык" value={result.language} />
          <MetaRow label="Длительность" value={formatDuration(result.duration_sec)} />
          <MetaRow
            label="Обработка"
            value={`${result.processing_sec.toFixed(1)} сек (${
              (result.duration_sec / result.processing_sec).toFixed(2)
            }× RT)`}
          />
		  {result.model_used && <MetaRow label="Модель" value={result.model_used} />}
          <MetaRow label="Сегментов" value={result.segments.length} />
          {result.translated && <MetaRow label="Переведено на" value="en" />}
        </>
      )}
      {task.exported_files?.length > 0 && (
        <MetaRow label="Сохранено файлов" value={task.exported_files.length} />
      )}
    </div>
  );
}

function MetaRow({ label, value, mono }) {
  return (
    <div className="meta-row">
      <span className="meta-label">{label}:</span>
      <span className={mono ? "meta-value-mono" : "meta-value"}>{value}</span>
    </div>
  );
}

function ExportButtons({ taskId }) {
  const baseUrl = `/api/tasks/${taskId}/export`;
  return (
    <div className="export-buttons">
      <strong>Скачать:</strong>
      <a className="btn-export" href={`${baseUrl}/txt`}>TXT</a>
      <a className="btn-export" href={`${baseUrl}/srt`}>SRT</a>
      <a className="btn-export" href={`${baseUrl}/vtt`}>VTT</a>
      <a className="btn-export" href={`${baseUrl}/json`}>JSON</a>
      <a className="btn-export" href={`${baseUrl}/docx?style=plain`}>DOCX простой</a>
      <a className="btn-export" href={`${baseUrl}/docx?style=timecoded`}>DOCX + таймкоды</a>
      <a className="btn-export" href={`${baseUrl}/docx?style=full`}>DOCX + спикеры</a>
    </div>
  );
}

function SegmentsView({ segments, currentTime, onSeek }) {
  if (segments.length === 0) {
    return <div className="muted">Сегментов нет.</div>;
  }
  return (
    <div className="segments">
      <h3>Текст ({segments.length} сегментов)</h3>
      <div className="segments-list">
        {segments.map((seg, i) => {
          const isActive = currentTime >= seg.start && currentTime < seg.end;
          return (
            <div
              key={i}
              className={`segment ${isActive ? "segment-active" : ""}`}
              onClick={() => onSeek(seg.start)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSeek(seg.start);
                }
              }}
            >
              <div className="segment-header">
                <span className="segment-time">
                  {formatTime(seg.start)} → {formatTime(seg.end)}
                </span>
                {seg.speaker && (
                  <span className="segment-speaker">{seg.speaker}</span>
                )}
              </div>
              <div className="segment-text">{seg.text}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------- Helpers ----------

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

function formatTime(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h) return `${pad(h)}:${pad(m)}:${pad(s)}`;
  return `${pad(m)}:${pad(s)}`;
}

function formatDuration(seconds) {
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h) return `${h} ч ${m} мин ${s} сек`;
  if (m) return `${m} мин ${s} сек`;
  return `${s} сек`;
}

function pad(n) {
  return String(n).padStart(2, "0");
}
