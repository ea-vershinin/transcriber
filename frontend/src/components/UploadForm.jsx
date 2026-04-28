import { useState } from "react";
import { submitUploadFile } from "../api";
import ModelSelector from "./ModelSelector";

export default function UploadForm() {
  const [file, setFile] = useState(null);
  const [diarize, setDiarize] = useState(false);
  const [model, setModel] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState(null);
  const [dragOver, setDragOver] = useState(false);

  async function handleSubmit() {
    if (!file) {
      setMessage({ type: "error", text: "Выберите файл" });
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const options = { diarize };
      if (model) options.model = model;
      const result = await submitUploadFile(file, options);
      setMessage({ type: "success", text: `Задача создана: ${result.task_id}` });
      setFile(null);
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    } finally {
      setSubmitting(false);
    }
  }

  function handleDragOver(e) {
    e.preventDefault();
    setDragOver(true);
  }
  function handleDragLeave(e) {
    e.preventDefault();
    setDragOver(false);
  }
  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) setFile(dropped);
  }

  return (
    <div className="form">
      <div
        className={`drop-zone ${dragOver ? "drop-zone-over" : ""}`}
        onDragEnter={handleDragOver}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {file ? (
          <div>
            <div className="drop-zone-filename">{file.name}</div>
            <div className="muted">
              {(file.size / 1024 / 1024).toFixed(1)} МБ
            </div>
            <button
              type="button"
              className="btn-text"
              onClick={() => setFile(null)}
              disabled={submitting}
            >
              Убрать
            </button>
          </div>
        ) : (
          <>
            <div className="drop-zone-main">Перетащите файл сюда</div>
            <div className="muted">или</div>
            <label className="btn-secondary">
              Выбрать файл
              <input
                type="file"
                accept="audio/*,video/*,.mp3,.wav,.m4a,.mp4,.avi,.mkv,.mov,.webm"
                onChange={(e) => setFile(e.target.files[0] ?? null)}
                disabled={submitting}
                style={{ display: "none" }}
              />
            </label>
            <div className="muted" style={{ marginTop: "0.5rem", fontSize: "0.8rem" }}>
              Поддерживаются: mp3, wav, m4a, mp4, avi, mkv, mov, webm
            </div>
          </>
        )}
      </div>

      <label className="form-row">
        <span>Модель Whisper:</span>
        <ModelSelector value={model} onChange={setModel} disabled={submitting} />
      </label>

      <label className="form-row form-checkbox">
        <input
          type="checkbox"
          checked={diarize}
          onChange={(e) => setDiarize(e.target.checked)}
          disabled={submitting}
        />
        <span>Диаризация (разделить по спикерам)</span>
      </label>

      <button
        className="btn-primary"
        onClick={handleSubmit}
        disabled={submitting || !file}
      >
        {submitting ? "Загружаем…" : "Загрузить и транскрибировать"}
      </button>

      {message && (
        <div className={`message message-${message.type}`}>{message.text}</div>
      )}
    </div>
  );
}
