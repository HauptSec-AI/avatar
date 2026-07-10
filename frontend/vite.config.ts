import { resolve } from "node:path";
import { defineConfig } from "vite";

// /admin is intentionally proxied straight to the backend (not served by Vite) even
// in dev, so admin auth/session cookies always talk to the real server. Build the
// frontend and load it from the backend to iterate on /admin. See README.md.
export default defineConfig({
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/admin": "http://localhost:8000",
    },
  },
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, "index.html"),
        admin: resolve(__dirname, "admin.html"),
      },
    },
  },
});
