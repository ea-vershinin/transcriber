import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Всё, что начинается с /api, пробрасывается на наш FastAPI.
    // Для фронтенда это выглядит как обращение на тот же хост,
    // поэтому никаких проблем с CORS.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
