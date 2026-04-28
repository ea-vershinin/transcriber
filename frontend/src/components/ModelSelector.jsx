import { useEffect, useState } from "react";
import { getModelsInfo } from "../api";

/**
 * Выпадающий список моделей Whisper.
 *
 * Поведение сохранения:
 *   - При маунте компонент читает localStorage["whisper_model_choice"].
 *   - Если там валидное значение (есть в available с бэка) — выставляет его
 *     в форме через onChange(savedValue).
 *   - При каждом изменении сохраняет новый выбор.
 *   - Пустая строка "" = "По умолчанию" — тоже сохраняется.
 *
 * Props:
 *   value — текущее значение (имя модели) или "" для "по умолчанию"
 *   onChange(name) — колбэк при изменении
 *   disabled — блокировка во время submit
 */
const STORAGE_KEY = "whisper_model_choice";

export default function ModelSelector({ value, onChange, disabled }) {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);

  // Загрузка списка моделей + применение сохранённого выбора.
  useEffect(() => {
    let cancelled = false;
    getModelsInfo()
      .then((data) => {
        if (cancelled) return;
        setInfo(data);

        // Если родитель ещё не задал значение — пробуем восстановить
        // из localStorage.
        if (value === "" || value === undefined || value === null) {
          const saved = localStorage.getItem(STORAGE_KEY);
          // Пустая строка = явный выбор "По умолчанию" — тоже валиден.
          // Реальное имя модели валидно, только если оно есть в available.
          if (saved === "") {
            // Уже пустая — ничего не делаем.
          } else if (saved && data.available.includes(saved)) {
            onChange(saved);
          } else if (saved) {
            // Сохранённое имя больше не в списке — чистим storage.
            localStorage.removeItem(STORAGE_KEY);
          }
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
    // Запускаем один раз — при монтировании. Мы сознательно не подписываемся
    // на value здесь, это начальная инициализация.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleChange(e) {
    const newValue = e.target.value;
    onChange(newValue);
    // Сохраняем сразу — и пустая строка ("По умолчанию") тоже сохраняется,
    // чтобы пользователь мог вернуться к дефолту и это запомнилось.
    try {
      localStorage.setItem(STORAGE_KEY, newValue);
    } catch {
      // localStorage может быть недоступен (Private mode, квота) — игнорируем.
    }
  }

  if (error) {
    return <div className="error">Не удалось загрузить модели: {error}</div>;
  }

  if (!info) {
    return <div className="muted">Загрузка списка моделей…</div>;
  }

  return (
    <select
      className="select-input"
      value={value}
      onChange={handleChange}
      disabled={disabled}
    >
      <option value="">По умолчанию ({info.default})</option>
      {info.available.map((name) => (
        <option key={name} value={name}>
          {name}
        </option>
      ))}
    </select>
  );
}
