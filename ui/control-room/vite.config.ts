import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// Fixed output names: every static response is already Cache-Control: no-store, and content
// hashes would turn each rebuild into a bin/deploy --prune. The committed build lives at
// bin/control_room_ui/app/ so rsync ships it and the drift check compares it without Node.
const outDir = process.env.VITE_OUT_DIR ?? path.resolve(__dirname, "../../bin/control_room_ui/app");
const proxyTarget = process.env.VITE_API_PROXY;

export default defineConfig({
  base: "/app/",
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir,
    emptyOutDir: true,
    sourcemap: false,
    modulePreload: { polyfill: false },
    rollupOptions: {
      output: {
        entryFileNames: "assets/app.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: (info) => {
          const name = info.names?.[0] ?? "";
          if (name.endsWith(".css")) return "assets/app.css";
          return "assets/[name][extname]";
        },
      },
    },
  },
  server: proxyTarget
    ? { proxy: { "/api": { target: proxyTarget, changeOrigin: false } } }
    : undefined,
});
