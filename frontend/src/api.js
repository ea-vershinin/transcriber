/**
 * API-клиент: тонкая обёртка над fetch.
 */

async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      if (data.detail) {
        detail = typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail);
      }
    } catch {
      // noop
    }
    throw new Error(`HTTP ${response.status}: ${detail}`);
  }
  // 204 No Content — тела нет
  if (response.status === 204) return null;
  return response.json();
}

// ---------- Tasks ----------

export function listTasks() {
  return request("/api/tasks");
}

export function getModelsInfo() {
  return request("/api/config/models");
}

export function getTask(taskId) {
  return request(`/api/tasks/${taskId}`);
}

export function deleteTask(taskId) {
  return request(`/api/tasks/${taskId}`, { method: "DELETE" });
}

/** URL для <audio src="..."> — браузер сам сделает GET с Range. */
export function getAudioUrl(taskId) {
  return `/api/tasks/${taskId}/audio`;
}

export function searchTasks(query, limit = 50) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return request(`/api/tasks/search?${params}`);
}

// ---------- Filesystem ----------

export function browseFolder(path = "") {
  const params = new URLSearchParams({ path });
  return request(`/api/fs/browse?${params}`);
}


// ---------- Transcription ----------

export function submitYouTube(url, options = {}) {
  return request("/api/transcribe/youtube", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, options }),
  });
}

export function submitLocalFile(path, options = {}, autoExport = [], force = false) {
  return request("/api/transcribe/local", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, options, auto_export: autoExport, force }),
  });
}

export function submitFolder(path, recursive, options = {}, autoExport = [], force = false) {
  return request("/api/transcribe/folder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      path,
      recursive,
      options,
      auto_export: autoExport,
      force,
    }),
  });
}

export async function submitUploadFile(file, options = {}) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("options", JSON.stringify(options));

  const response = await fetch("/api/transcribe/file", {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      if (data.detail) detail = JSON.stringify(data.detail);
    } catch {
      // noop
    }
    throw new Error(`HTTP ${response.status}: ${detail}`);
  }
  return response.json();
}
