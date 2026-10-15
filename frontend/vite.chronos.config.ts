// Builds the Chronos workspace into Chronos's static folder, the way
// `vite.config.ts` builds Akasha's research studio into Akasha's and
// `vite.logos.config.ts` the writing page into Logos's: a separate build per
// Flask app, because each app serves only its own static folder. The manifest
// is how the page shell (chronos/workspace_page.py) finds the hashed files;
// `base: "./"` keeps chunk URLs relative, so the bundle works at `/` and behind
// the gateway at `/timeline` alike.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../src/visualizer/chronos/static/workspace",
    emptyOutDir: true,
    manifest: true,
    rolldownOptions: { input: "src/chronos/main.tsx" },
  },
});
