import { useState } from "react";
import { submitYouTube } from "../api";
import ModelSelector from "./ModelSelector";

export default function YouTubeForm() {
  const [url, setUrl] = useState("");
  const [diarize, setDiarize] = useState(false);
  const [model, setModel] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState(null);

  async function handleSubmit() {
    if (!url.trim()) {
      setMessage({ type: "error", text: "Вставьте ссылку" });
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const options = { diarize };
      if (model) options.model = model;
      const result = await submitYouTube(url.trim(), options);
      setMessage({ type: "success", text: `Задача создана: ${result.task_id}` });
      setUrl("");
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="form">
      <label className="form-row">
        <span>Ссылка на YouTube:</span>
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.youtube.com/watch?v=..."
          disabled={submitting}
        />
      </label>

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
        disabled={submitting}
      >
        {submitting ? "Отправляем…" : "Скачать и транскрибировать"}
      </button>

      {message && (
        <div className={`message message-${message.type}`}>{message.text}</div>
      )}
    </div>
  );
}
