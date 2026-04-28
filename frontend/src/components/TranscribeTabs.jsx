import { useState } from "react";
import FolderForm from "./FolderForm";
import YouTubeForm from "./YouTubeForm";
import UploadForm from "./UploadForm";

const TABS = [
  { id: "folder", label: "Папка", Component: FolderForm },
  { id: "youtube", label: "YouTube", Component: YouTubeForm },
  { id: "upload", label: "Загрузить файл", Component: UploadForm },
];

export default function TranscribeTabs() {
  const [activeId, setActiveId] = useState("folder");
  const ActiveComponent = TABS.find((t) => t.id === activeId).Component;

  return (
    <div className="tabs">
      <div className="tabs-nav">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`tab ${tab.id === activeId ? "tab-active" : ""}`}
            onClick={() => setActiveId(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="tabs-content">
        <ActiveComponent />
      </div>
    </div>
  );
}
