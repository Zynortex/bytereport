import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import fs from "fs";
import path from "path";

// Where the site is served. Link previews need absolute URLs for og:url and
// og:image. Override with VITE_SITE_URL when the domain changes.
const SITE_URL = (process.env.VITE_SITE_URL || "https://bytereport-frontend.vercel.app").replace(/\/$/, "");

// The demo report gets its own preview card: a link to /demo shared in
// Telegram should say "sample report", not repeat the landing page.
const DEMO_META = {
  url: `${SITE_URL}/demo`,
  title: "Пример отчёта ByteReport — мебельная мастерская «Контур»",
  description: "I квартал 2024: прибыль, кассовый разрыв, риски и приоритетные действия — так выглядит отчёт ByteReport по банковской выписке.",
  image: `${SITE_URL}/og-demo.png`,
};

function setMeta(html: string, key: string, value: string): string {
  const re = new RegExp(`(<meta (?:property|name)="${key.replace(/[.:]/g, "\\$&")}" content=")[^"]*(")`);
  return html.replace(re, `$1${value}$2`);
}

/**
 * Fills __SITE_URL__ in index.html and, after a production build, writes the
 * /demo copy (dist/demo/index.html and dist/demo.html) with the demo's preview
 * tags. The static host serves a real file before the SPA rewrite, so a
 * crawler fetching /demo reads these tags; the app itself is the same bundle.
 */
function socialMeta(): Plugin {
  let isBuild = false;
  return {
    name: "bytereport-social-meta",
    configResolved(config) { isBuild = config.command === "build"; },
    transformIndexHtml: (html) => html.split("__SITE_URL__").join(SITE_URL),
    closeBundle() {
      if (!isBuild) return;
      const dist = path.resolve(__dirname, "dist");
      const index = path.join(dist, "index.html");
      if (!fs.existsSync(index)) return;
      let html = fs.readFileSync(index, "utf8");
      html = html.replace(/<title>[^<]*<\/title>/, `<title>${DEMO_META.title}</title>`);
      html = setMeta(html, "description", DEMO_META.description);
      html = setMeta(html, "og:url", DEMO_META.url);
      html = setMeta(html, "og:title", DEMO_META.title);
      html = setMeta(html, "og:description", DEMO_META.description);
      html = setMeta(html, "og:image", DEMO_META.image);
      html = setMeta(html, "og:image:alt", DEMO_META.title);
      fs.mkdirSync(path.join(dist, "demo"), { recursive: true });
      fs.writeFileSync(path.join(dist, "demo", "index.html"), html);
      fs.writeFileSync(path.join(dist, "demo.html"), html);
    },
  };
}

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),   // Tailwind v4: Vite plugin replaces PostCSS
    socialMeta(),
  ],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  build: {
    rollupOptions: {
      output: {
        // Libraries in their own chunks: each stays under the 500 kB warning,
        // and a release that only changes our code does not invalidate the
        // browser's copy of React or Supabase.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (/[\\/]node_modules[\\/](react|react-dom|scheduler|react-router|react-router-dom)[\\/]/.test(id)) return "vendor-react";
          if (id.includes("@supabase")) return "vendor-supabase";
          if (/[\\/]node_modules[\\/](i18next|react-i18next)[\\/]/.test(id)) return "vendor-i18n";
          if (/[\\/]node_modules[\\/](motion|framer-motion|motion-dom|motion-utils)[\\/]/.test(id)) return "vendor-motion";
          return undefined;
        },
      },
    },
  },
  server: {
    port: 5173,
  },
});
