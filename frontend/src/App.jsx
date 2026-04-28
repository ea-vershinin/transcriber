import { Link, Route, Routes } from "react-router-dom";
import HomePage from "./pages/HomePage";
import TaskPage from "./pages/TaskPage";

/**
 * Главный компонент.
 *
 * Роуты:
 *   /            → HomePage (формы + история)
 *   /tasks/:id   → TaskPage (детали одной задачи)
 */
export default function App() {
  return (
    <div className="container">
      <header className="app-header">
        <h1>
          <Link to="/" className="app-title">Transcriber</Link>
        </h1>
        <p className="hint">
          Локальная транскрибация через WhisperX.
          Результаты сохраняются рядом с исходными файлами.
        </p>
      </header>

      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/tasks/:taskId" element={<TaskPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  );
}

function NotFound() {
  return (
    <div className="section">
      <h2>404</h2>
      <p>Страница не найдена.</p>
      <Link to="/" className="back-link">← Вернуться на главную</Link>
    </div>
  );
}
