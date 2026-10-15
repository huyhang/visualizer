// Builds the Logos writing page into Logos's static folder, the way
// `vite.config.ts` builds Akasha's research studio into Akasha's: a separate
// build per Flask app, because each app serves only its own static folder.
// The manifest is how the page shell (logos/writer_page.py) finds the hashed
// files; `base: "./"` keeps chunk URLs relative, so the bundle works at `/` and
// behind the gateway at `/logos` alike.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../src/visualizer/logos/static/writer",
    emptyOutDir: true,
    manifest: true,
    rolldownOptions: { input: "src/logos/main.tsx" },
  },
});
