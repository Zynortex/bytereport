import { create } from "zustand";
import { API_URL } from "./baseUrl";

/**
 * The backend runs on a free host that sleeps after 15 minutes without a
 * request and needs up to a minute to wake. Without this, the first click
 * after a quiet spell looked like a frozen button.
 *
 * Every API request first calls ensureServerAwake(). When the server is known
 * to be up (it answered something in the last few minutes) that costs nothing.
 * Otherwise /health is probed; if it has not answered within 3 seconds the
 * wake screen appears, probing continues for up to 90 seconds, and the
 * original request goes out by itself the moment the server answers. After
 * 90 seconds the screen says so plainly and offers to try again.
 *
 * The screen depends on /health alone. The request itself is never timed:
 * a full AI analysis takes 30-45 seconds and a long PDF several more, and a
 * slow but live request is not a sleeping server. Nor is a server that
 * answers but cannot be read (a CORS mistake): see serverAnswers().
 *
 * Not in development (npm run dev): there the backend is a local process the
 * developer started or did not, and a wake screen only gets in the way.
 */

/** Off under `npm run dev`; on in every build. */
export const WAKE_SCREEN_ENABLED = !import.meta.env.DEV;

export const SHOW_AFTER_MS = 3_000;
export const GIVE_UP_AFTER_MS = 90_000;
/** What the screen promises ("up to a minute"); the progress bar fills over it. */
export const EXPECTED_WAKE_MS = 60_000;
// A sleeping host holds the connection open while it boots, so one probe may
// legitimately wait most of a minute before it is answered.
const PROBE_TIMEOUT_MS = 30_000;
const PROBE_PAUSE_MS = 2_000;
// The host sleeps after 15 idle minutes; after 10 without hearing from it, ask again.
const AWAKE_FOR_MS = 10 * 60_000;

export type WakePhase = "idle" | "waking" | "failed";

interface WakeState {
  phase: WakePhase;
  /** When the current attempt began: the progress bar and the seconds count. */
  startedAt: number;
  retry: () => void;
  dismiss: () => void;
}

let awakeUntil = 0;
let inflight: Promise<void> | null = null;
let decide: ((tryAgain: boolean) => void) | null = null;

export const useServerWake = create<WakeState>(() => ({
  phase: "idle",
  startedAt: 0,
  retry: () => decide?.(true),
  dismiss: () => decide?.(false),
}));

/** The visitor closed the wake screen after it gave up. */
export class ServerAsleepError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ServerAsleepError";
  }
}

/** Any answer from the server — success or an HTTP error — proves it is up. */
export function markAwake(): void {
  awakeUntil = Date.now() + AWAKE_FOR_MS;
}

/** No answer at all: the next request checks before it is sent. */
export function markUnknown(): void {
  awakeUntil = 0;
}

export function isKnownAwake(): boolean {
  return Date.now() < awakeUntil;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** fetch with a deadline. Rejects with the AbortError when it runs out. */
async function fetchWithin(timeoutMs: number, init: RequestInit): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(`${API_URL}/health`, { ...init, cache: "no-store", credentials: "omit", signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Does the API process answer /health at all? Only "no" may show the wake
 * screen.
 *
 * Normally the answer is read: 200 and {"status":"ok"}. A response that is not
 * that (a gateway's 502 while the host restarts) is not the API yet.
 *
 * When the request fails without any readable response, that alone does not
 * mean the server is asleep: a CORS mistake looks exactly the same from here.
 * A second, no-cors request settles it: the browser does not let us read its
 * answer, but it resolves only when an answer arrived. An answer means a live
 * server; the real request then fails with its own, visible error instead of
 * a "server is starting" screen that would never end.
 */
async function serverAnswers(timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  try {
    const res = await fetchWithin(timeoutMs, {});
    if (!res.ok) return false;
    const body = (await res.json().catch(() => null)) as { status?: string } | null;
    return body?.status === "ok";
  } catch (err) {
    // Our own deadline ran out: no answer. A sleeping host holds the
    // connection open, so this is the usual way a sleeping server looks.
    if (err instanceof DOMException && err.name === "AbortError") return false;
  }
  try {
    await fetchWithin(Math.max(1_000, Math.min(5_000, deadline - Date.now())), { mode: "no-cors" });
    return true;
  } catch {
    return false;   // nothing answered: refused, unreachable, or asleep
  }
}

async function answersWithin(budgetMs: number): Promise<boolean> {
  const end = Date.now() + budgetMs;
  while (Date.now() < end) {
    if (await serverAnswers(Math.min(PROBE_TIMEOUT_MS, Math.max(1_000, end - Date.now())))) return true;
    await sleep(Math.min(PROBE_PAUSE_MS, Math.max(0, end - Date.now())));
  }
  return false;
}

async function wake(gaveUpMessage: () => string): Promise<void> {
  const set = useServerWake.setState;
  let startedAt = Date.now();
  // Not shown at once: an awake server answers in milliseconds, and a screen
  // that flashes for 50 ms is worse than none.
  const reveal = setTimeout(() => set({ phase: "waking", startedAt }), SHOW_AFTER_MS);
  try {
    for (;;) {
      if (await answersWithin(GIVE_UP_AFTER_MS)) {
        markAwake();
        return;
      }
      clearTimeout(reveal);
      set({ phase: "failed" });
      const tryAgain = await new Promise<boolean>((resolve) => { decide = resolve; });
      decide = null;
      if (!tryAgain) throw new ServerAsleepError(gaveUpMessage());
      startedAt = Date.now();
      set({ phase: "waking", startedAt });
    }
  } finally {
    clearTimeout(reveal);
    set({ phase: "idle" });
  }
}

/**
 * Resolves once the server answers; rejects with ServerAsleepError if the
 * visitor gives up. Concurrent callers share one wake-up.
 */
export function ensureServerAwake(gaveUpMessage: () => string): Promise<void> {
  if (!WAKE_SCREEN_ENABLED || isKnownAwake()) return Promise.resolve();
  inflight ??= wake(gaveUpMessage).finally(() => { inflight = null; });
  return inflight;
}

let warmed = false;

/**
 * Start waking the server without waiting for it: once per visit, silently.
 * Called where a visitor is about to need the backend (the landing page, the
 * sign-in page, a demo link into the product) so it is up by the time they
 * click. A sleeping host accepts the connection and holds it, so nothing is
 * logged while it boots; the answer, when it comes, marks the server awake.
 */
export function warmUp(): void {
  if (!WAKE_SCREEN_ENABLED || warmed || isKnownAwake()) return;
  warmed = true;
  try {
    if (sessionStorage.getItem("br_warm")) return;
    sessionStorage.setItem("br_warm", "1");
  } catch {
    // Storage blocked (private mode): the module flag still limits it to once.
  }
  void serverAnswers(GIVE_UP_AFTER_MS).then((ok) => { if (ok) markAwake(); });
}

/** Props that warm the server when a visitor reaches for a link into the product. */
export const warmOnIntent = {
  onPointerEnter: warmUp,
  onFocus: warmUp,
  onTouchStart: warmUp,
} as const;
