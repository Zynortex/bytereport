/**
 * The backend's origin. VITE_API_URL is baked in at build time (Vercel →
 * Settings → Environment Variables, then redeploy). `||`, not `??`: an empty
 * value in a .env file must fall back too, not turn every request relative.
 */
export const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/+$/, "");
