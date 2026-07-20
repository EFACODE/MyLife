/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// API path prefixes proxied to the backend in `npm run dev`, so the SPA talks to
// the API same-origin (no CORS needed). Edit the target here, or set
// VITE_API_BASE_URL for a non-proxied build.
const API_TARGET = "http://127.0.0.1:8000";
const API_PREFIXES = [
  "/auth",
  "/users",
  "/households",
  "/consents",
  "/audit",
  "/me",
  "/timeline",
  "/accounts",
  "/finance",
  "/health",
  "/goals",
  "/documents",
  "/memory",
  "/knowledge-graph",
  "/assistant",
  "/insights",
  "/briefing",
  "/forecasts",
];

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(API_PREFIXES.map((prefix) => [prefix, API_TARGET])),
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
