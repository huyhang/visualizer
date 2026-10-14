// Builds the studio into Akasha's static folder, where Flask serves it. The
// manifest is how the page shell (akasha/studio_routes.py) finds the hashed
// files; `base: "./"` keeps every chunk and asset URL relative to the entry,
// so the bundle works wherever Akasha is mounted.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../src/visualizer/akasha/static/studio",
    emptyOutDir: true,
    manifest: true,
    rolldownOptions: { input: "src/main.tsx" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
