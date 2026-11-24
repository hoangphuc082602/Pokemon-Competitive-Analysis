import { defineConfig } from "vite";

// Relative base: the site works at https://<user>.github.io/<repo>/ and locally without changes.
// Four pages: the Meta Overview (index.html), Insights (insights.html, #15), the Damage calc (calc.html, #16) and the Team builder (team.html, #17).
// fs.allow: the calc page bundles the Python engine files from ../python as text (?raw) in the dev server too.
export default defineConfig({
  base: "./",
  build: { rollupOptions: { input: { main: "index.html", insights: "insights.html", calc: "calc.html", team: "team.html" } } },
  server: { fs: { allow: [".."] } },
  test: { environment: "node" },
} as Parameters<typeof defineConfig>[0]);
