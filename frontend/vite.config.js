import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { loadProjectEnv } from "./scripts/env-file.mjs";
import { getWebmasterMetaTags } from "./scripts/webmaster-verification.mjs";

loadProjectEnv();

const backendUrl = process.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";
const siteUrl = (process.env.PUBLIC_SITE_URL || process.env.VITE_PUBLIC_SITE_URL || "https://saveany.local").replace(/\/+$/, "");

export default defineConfig({
  plugins: [
    {
      name: "seo-site-url-html",
      transformIndexHtml(html) {
        return html.replaceAll("__SEO_SITE_URL__", siteUrl).replaceAll("__SEO_WEBMASTER_META__", getWebmasterMetaTags());
      }
    },
    vue(),
    tailwindcss()
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": backendUrl,
      "/files": backendUrl
    }
  }
});
