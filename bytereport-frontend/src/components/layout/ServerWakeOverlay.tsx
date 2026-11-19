import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { EXPECTED_WAKE_MS, useServerWake } from "@/api/serverWake";
import { useExitAnimation } from "@/lib/motion";
import { cn } from "@/lib/utils";

/**
 * Shown while a sleeping backend boots (see api/serverWake.ts). The request
 * that triggered it is not lost: it waits, and goes out by itself the moment
 * the server answers. The bar fills over the minute the text promises and
 * holds short of the end — it measures time spent, not progress it cannot know.
 */
export function ServerWakeOverlay() {
  const { t } = useTranslation();
  const { phase, startedAt, retry, dismiss } = useServerWake();
  const { mounted, closing } = useExitAnimation(phase !== "idle", 150);
  const [now, setNow] = useState(() => Date.now());
  const retryRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (phase !== "waking") return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, [phase]);

  useEffect(() => {
    if (phase !== "failed") return;
    retryRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") dismiss(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, dismiss]);

  if (!mounted) return null;

  const failed = phase === "failed";
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));
  const filled = failed ? 100 : Math.min(95, ((now - startedAt) / EXPECTED_WAKE_MS) * 100);

  return (
    <div className={cn("fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4",
                       closing ? "anim-fade-out" : "anim-fade-in")}>
      <div
        role={failed ? "alertdialog" : "status"}
        aria-live="polite"
        aria-modal={failed ? true : undefined}
        aria-labelledby="wake-title"
        aria-describedby="wake-text"
        className={cn("w-full max-w-md border border-brand-border bg-header rounded-xs p-6",
                      closing ? "anim-pop-out" : "anim-pop-in")}
      >
        <div className="flex items-baseline justify-between gap-4 mb-2">
          <h2 id="wake-title" className="font-heading text-base font-semibold text-brand-dark text-balance">
            {failed ? t("server_wake.failed_title") : t("server_wake.title")}
          </h2>
          {!failed && (
            <span className="font-mono text-xs tabular-nums text-brand-muted shrink-0" aria-hidden="true">
              {t("server_wake.elapsed", { s: seconds })}
            </span>
          )}
        </div>
        <p id="wake-text" className="text-sm text-brand-muted leading-relaxed mb-5">
          {failed ? t("server_wake.failed_text") : t("server_wake.text")}
        </p>

        <div className="h-px w-full bg-line overflow-hidden" aria-hidden="true">
          <div
            className={cn("h-full transition-[width] duration-500 ease-linear motion-reduce:transition-none",
                          failed ? "bg-sev-high-fg" : "bg-accent-fg")}
            style={{ width: `${filled}%` }}
          />
        </div>

        {failed && (
          <div className="mt-6 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
            <Button variant="outline" onClick={dismiss}>{t("server_wake.close")}</Button>
            <Button ref={retryRef} onClick={retry}>{t("server_wake.retry")}</Button>
          </div>
        )}
      </div>
    </div>
  );
}
