import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  esbuild: {
    jsx: "automatic",
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    // Browser specs are executed by Playwright, not inside the jsdom suite.
    exclude: [
      "**/node_modules/**",
      "**/.git/**",
      "**/dist/**",
      "**/cypress/**",
      "**/.{idea,cache,output,temp}/**",
      "e2e/**",
    ],
  },
});
