import { defineConfig } from "vite";

// Relative base: the site works at https://<user>.github.io/<repo>/ and locally without changes.
// Two pages: the Meta Overview (index.html) and the Insights page (insights.html, #15).
export default defineConfig({
  base: "./",
  build: { rollupOptions: { input: { main: "index.html", insights: "insights.html" } } },
  test: { environment: "node" },
} as Parameters<typeof defineConfig>[0]);
