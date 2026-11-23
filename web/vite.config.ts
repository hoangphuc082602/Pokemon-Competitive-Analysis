import { defineConfig } from "vite";

// Relative base: the site works at https://<user>.github.io/<repo>/ and locally without changes.
export default defineConfig({
  base: "./",
  test: { environment: "node" },
} as Parameters<typeof defineConfig>[0]);
