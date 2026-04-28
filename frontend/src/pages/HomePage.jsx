import TranscribeTabs from "../components/TranscribeTabs";
import TasksList from "../components/TasksList";

/**
 * Главная страница: формы для новых задач + список истории.
 * Содержимое совпадает с тем, что было в App.jsx до роутинга.
 */
export default function HomePage() {
  return (
    <>
      <section className="section">
        <h2>Новая задача</h2>
        <TranscribeTabs />
      </section>

      <section className="section">
        <h2>История</h2>
        <TasksList />
      </section>
    </>
  );
}
