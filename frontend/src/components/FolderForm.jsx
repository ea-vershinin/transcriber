import { useState } from "react";
import { submitFolder } from "../api";
import FolderPicker from "./FolderPicker";
import ModelSelector from "./ModelSelector";

export default function FolderForm() {
  const [path, setPath] = useState("");
  const [recursive, setRecursive] = useState(true);
  const [force, setForce] = useState(false);
  const [model, setModel] = useState("");
  const [autoExport, setAutoExport] = useState(["docx_timecoded"]);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState(null);
  const [pickerOpen, setPickerOpen] = useState(false);

  const toggleFormat = (fmt) => {
    setAutoExport((prev) =>
      prev.includes(fmt) ? prev.filter((f) => f !== fmt) : [...prev, fmt]
    );
  };

  async function handleSubmit() {
    if (!path.trim()) {
      setMessage({ type: "error", text: "Укажите путь к папке" });
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const options = model ? { model } : {};
      const result = await submitFolder(
        path.trim(), recursive, options, autoExport, force
      );
      // Собираем сообщение, показывая и запущенные, и пропущенные.
      const parts = [
        `Найдено файлов: ${result.files_found}`,
        `Запущено: ${result.task_ids.length}`,
      ];
      if (result.skipped > 0) {
        parts.push(`пропущено (уже обработаны): ${result.skipped}`);
      }
      setMessage({ type: "success", text: parts.join(". ") + "." });
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="form">
      <label className="form-row">
        <span>Путь к папке:</span>
        <div className="path-input-row">
          <input
            type="text"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="C:/Courses/Python"
            disabled={submitting}
          />
          <button
            type="button"
            className="btn-secondary"
            onClick={() => setPickerOpen(true)}
            disabled={submitting}
          >
            Обзор…
          </button>
        </div>
      </label>

      <label className="form-row form-checkbox">
        <input
          type="checkbox"
          checked={recursive}
          onChange={(e) => setRecursive(e.target.checked)}
          disabled={submitting}
        />
        <span>Рекурсивно (включая вложенные папки)</span>
      </label>

      <label className="form-row form-checkbox">
        <input
          type="checkbox"
          checked={force}
          onChange={(e) => setForce(e.target.checked)}
          disabled={submitting}
        />
        <span>
          Обработать заново
          <span className="muted" style={{ marginLeft: "0.5rem", fontSize: "0.85rem" }}>
            (даже если файл уже есть в истории)
          </span>
        </span>
      </label>

      <label className="form-row">
        <span>Модель Whisper:</span>
        <ModelSelector value={model} onChange={setModel} disabled={submitting} />
      </label>

      <div className="form-row">
        <span>Автосохранение рядом с исходником:</span>
        <div className="format-checkboxes">
          {[
            ["docx_timecoded", "DOCX с таймкодами"],
            ["docx_plain", "DOCX простой"],
            ["docx_full", "DOCX + спикеры"],
            ["txt", "TXT"],
            ["srt", "SRT"],
            ["vtt", "VTT"],
            ["json", "JSON"],
          ].map(([fmt, label]) => (
            <label key={fmt} className="format-checkbox">
              <input
                type="checkbox"
                checked={autoExport.includes(fmt)}
                onChange={() => toggleFormat(fmt)}
                disabled={submitting}
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      <button
        className="btn-primary"
        onClick={handleSubmit}
        disabled={submitting}
      >
        {submitting ? "Запускаем…" : "Запустить обработку папки"}
      </button>

      {message && (
        <div className={`message message-${message.type}`}>{message.text}</div>
      )}

      {pickerOpen && (
        <FolderPicker
          initialPath={path}
          onSelect={(selected) => {
            setPath(selected);
            setPickerOpen(false);
          }}
          onClose={() => setPickerOpen(false)}
        />
      )}
    </div>
  );
}
