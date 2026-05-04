import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = "http://localhost:8000";
const proxied = ["/search", "/ask", "/papers", "/health", "/auth", "/subjects", "/conversations"];

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      proxied.map((p) => [p, { target: backend, changeOrigin: true }]),
    ),
  },
});
