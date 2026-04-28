import { useEffect, useState } from "react";
import { browseFolder } from "../api";

/**
 * Модальный браузер файловой системы.
 *
 * Props:
 *   initialPath — стартовая папка (или "" для списка дисков)
 *   onSelect(path) — колбэк при нажатии "Выбрать эту папку"
 *   onClose() — закрыть без выбора
 *
 * Реализовано как фиксированный оверлей + коробка в центре.
 * Клик по фону закрывает, клик по содержимому — нет
 * (проверяем e.target === e.currentTarget).
 */
export default function FolderPicker({ initialPath = "", onSelect, onClose }) {
  const [path, setPath] = useState(initialPath);
  const [listing, setListing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Закрытие по Esc — удобно.
  useEffect(() => {
    function handleKey(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  // Загружаем содержимое при изменении path.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    browseFolder(path)
      .then((data) => {
        if (!cancelled) {
          setListing(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  // Клики по элементам — только папки кликабельны.
  function handleEntryClick(entry) {
    if (entry.is_dir) {
      setPath(entry.path);
    }
  }

  function handleGoUp() {
    if (listing?.parent !== null && listing?.parent !== undefined) {
      setPath(listing.parent);
    } else {
      // На корне диска поднимаемся в "список дисков"
      setPath("");
    }
  }

  function handleSelectCurrent() {
    if (path) {
      onSelect(path);
    }
  }

  return (
    <div
      className="modal-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-box">
        <div className="modal-header">
          <h3>Выберите папку</h3>
          <button
            type="button"
            className="btn-icon"
            onClick={onClose}
            title="Закрыть"
          >
            ×
          </button>
        </div>

        <div className="folder-picker-path">
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={handleGoUp}
            disabled={!listing || listing.parent === null && !path}
          >
            ↑ Вверх
          </button>
          <input
            type="text"
            className="folder-picker-path-input"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            onKeyDown={(e) => {
              // Enter перезагружает текущий путь (удобно если вручную ввели)
              if (e.key === "Enter") {
                e.preventDefault();
                // useEffect выше уже среагирует на изменение path
              }
            }}
            placeholder="Путь, или пусто для списка дисков"
          />
        </div>

        <div className="folder-picker-list">
          {loading && <div className="muted">Загрузка…</div>}
          {error && <div className="error">Ошибка: {error}</div>}
          {listing && !loading && !error && (
            <>
              {listing.entries.length === 0 && (
                <div className="muted">Папка пуста.</div>
              )}
              {listing.entries.map((entry) => (
                <div
                  key={entry.path}
                  className={`folder-picker-entry ${
                    entry.is_dir ? "folder-picker-entry-dir" : "folder-picker-entry-file"
                  }`}
                  onClick={() => handleEntryClick(entry)}
                  role={entry.is_dir ? "button" : undefined}
                  tabIndex={entry.is_dir ? 0 : -1}
                  onKeyDown={(e) => {
                    if (entry.is_dir && (e.key === "Enter" || e.key === " ")) {
                      e.preventDefault();
                      handleEntryClick(entry);
                    }
                  }}
                >
                  <span className="folder-picker-icon">
                    {entry.is_dir ? "📁" : "📄"}
                  </span>
                  <span className="folder-picker-name">{entry.name}</span>
                </div>
              ))}
            </>
          )}
        </div>

        <div className="modal-footer">
          <button
            type="button"
            className="btn-secondary"
            onClick={onClose}
          >
            Отмена
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={handleSelectCurrent}
            disabled={!path}
          >
            Выбрать эту папку
          </button>
        </div>
      </div>
    </div>
  );
}
