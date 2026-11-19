import axios from "axios";
import { supabase } from "@/lib/supabase";
import i18n from "@/i18n";
import { API_URL } from "./baseUrl";
import { ensureServerAwake, markAwake, markUnknown } from "./serverWake";

// ── User-friendly error messages ──────────────────────────────────────────────

const STATUS_MESSAGES: Record<number, string> = {
  // The backend now names its caller. Each of these has a distinct fix, so
  // they must not collapse into one "ошибка сервера".
  401: "Сессия истекла. Войдите в аккаунт заново.",
  403: "Доступ ограничен. Подтвердите email и используйте постоянный адрес.",
  429: "Слишком много запросов или исчерпан дневной лимит. Попробуйте позже.",
  413: "Файл слишком большой. Максимум 10 МБ.",
  422: "Неверный формат файла. Проверьте структуру CSV.",
  500: "Ошибка анализа на сервере. Попробуйте ещё раз.",
  502: "Сервер временно недоступен. Попробуйте через минуту.",
  503: "Сервис перегружен. Попробуйте через минуту.",
};

/**
 * An API failure with its HTTP status kept alongside the message.
 *
 * Callers need to branch on "the session is gone" versus anything else, and
 * matching on the message text would mean pattern-matching translated Russian —
 * which breaks the moment the backend rewords a detail or the user switches
 * language. The status is the stable fact.
 */
export class ApiError extends Error {
  readonly status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** True when the failure means "sign in again" and nothing else will help. */
export function isAuthError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}

export function parseApiError(err: unknown): string {
  if (!axios.isAxiosError(err)) {
    return err instanceof Error ? err.message : "Произошла неизвестная ошибка.";
  }

  // Timeout (axios code ECONNABORTED)
  if (err.code === "ECONNABORTED") {
    return "Анализ идёт дольше 3 минут. Похоже, AI-провайдер не отвечает — попробуйте ещё раз.";
  }

  // No response at all — server unreachable or CORS blocked
  if (!err.response) {
    return "Сервер недоступен. Проверьте соединение и попробуйте через минуту.";
  }

  const status = err.response.status;
  // FastAPI's own detail is more specific than our table whenever it exists —
  // "confirm your email" and "no throwaway addresses" are both 403 and need
  // different actions from the user.
  const detail = (err.response.data as { detail?: string })?.detail;
  if (detail && typeof detail === "string") return detail;
  if (status in STATUS_MESSAGES) return STATUS_MESSAGES[status];

  return `Ошибка сервера (${status}). Попробуйте ещё раз.`;
}

// ── Axios instance ────────────────────────────────────────────────────────────

export const apiClient = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
  // Must stay ABOVE the backend's own ceiling (settings.ai_timeout_seconds,
  // 120 s per attempt with SDK retries disabled). At the previous 120 s the two
  // were equal, so a slow-but-successful analysis raced the client: axios
  // aborted, the UI painted the in-flight step red, and the server went on to
  // log 200 OK. Measured range for this call is 15-140 s.
  timeout: 180_000,
});

/**
 * Attach a token that is actually current.
 *
 * `br_token` is a hand-kept mirror of the Supabase access token, written by the
 * auth store on sign-in and on the auth-state listener. It goes stale the
 * moment Supabase refreshes the session without that listener writing back, and
 * a stale token means a 401 on a request the user had every right to make.
 *
 * getSession() returns the live session and refreshes it if it has expired, so
 * the token handed to the backend is correct by construction. The mirror is
 * still updated because other code reads it, but nothing depends on it being
 * fresh any more.
 */
apiClient.interceptors.request.use(async (config) => {
  // A sleeping free host first: shows the wake screen if it takes over 3 s,
  // and holds this request until the server answers.
  await ensureServerAwake(() => i18n.t("server_wake.gave_up"));

  let token: string | null = null;
  try {
    const { data } = await supabase.auth.getSession();
    token = data.session?.access_token ?? null;
    if (token) localStorage.setItem("br_token", token);
  } catch {
    // Supabase unreachable — fall back to the mirror rather than sending
    // nothing at all, and let the backend decide.
    token = localStorage.getItem("br_token");
  }
  if (token) config.headers.Authorization = `Bearer ${token}`;
  // Server-written messages (e.g. "free reports are used up") come back in
  // the interface language.
  config.headers["Accept-Language"] = (i18n.language || "en").slice(0, 2);
  return config;
});

apiClient.interceptors.response.use(
  (res) => {
    markAwake();
    return res;
  },
  (err) => {
    // An HTTP error is still an answer. No answer at all (and not our own
    // long-request timeout) means the next request checks the server first.
    if (axios.isAxiosError(err)) {
      if (err.response) markAwake();
      else if (err.code !== "ECONNABORTED") markUnknown();
    }
    // A 401 used to do `window.location.href = "/auth"`. That was a silent
    // full-page navigation on top of an in-progress action, and it did not even
    // land on /auth: it cleared `br_token` but not the Supabase session, so the
    // reload restored the user, /auth bounced a signed-in visitor onward, and
    // the page landed on the Dashboard with no message. Recording a voice note
    // looked like it randomly navigated away.
    //
    // Worse, the reload rewrote `br_token` from the same session, so the next
    // attempt failed identically — a loop with no visible cause.
    //
    // Every error now comes back as a message for the caller to show in place.
    // Where the session really is gone, the page says so and offers a way back.
    return Promise.reject(
      new ApiError(parseApiError(err), err.response?.status)
    );
  }
);
