import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig(async () => ({
  plugins: [react()],

  // Vite options tailored for Tauri development and only Tauri.
  //
  // 1. Prevent Vite from obscuring rust errors
  clearScreen: false,
  // 2. Tauri expects a fixed port, fail if port is not available
  server: {
    port: 1420,
    strictPort: true,
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/api/, ""),
      },
      "/chat": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/voice": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/avatar": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
    watch: {
      // tell Vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
    },
  },

  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
}));
