import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Vehicle Service CRM — built by Sahil Thakur
const proxyTarget = process.env.VITE_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    sourcemap: false,
    rollupOptions: {
      output: {
        // Long-lived vendor chunks: app deploys don't invalidate the browser cache for libraries.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("@fullcalendar")) return "vendor-calendar";
          if (id.includes("recharts") || id.includes("d3-") || id.includes("victory")) return "vendor-charts";
          if (id.includes("react-router") || id.includes("/react-dom/") || id.includes("/react/") || id.includes("scheduler"))
            return "vendor-react";
          if (id.includes("@tanstack") || id.includes("axios") || id.includes("zod") || id.includes("react-hook-form"))
            return "vendor-data";
          return "vendor";
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: proxyTarget, changeOrigin: true },
      "/media": { target: proxyTarget, changeOrigin: true },
    },
  },
});
