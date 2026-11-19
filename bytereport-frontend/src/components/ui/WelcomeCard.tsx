import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { useExitAnimation } from "@/lib/motion";

const SEEN_KEY = "br_welcome_seen";
const LANG_KEY = "br_lang";
const APPEAR_DELAY_MS = 1000;
const EXIT_MS = 180;

const LANGS = [
  { code: "uz", label: "O'zbekcha" },
  { code: "ru", label: "Русский" },
  { code: "en", label: "English" },
];

const POINT_KEYS = ["p1", "p2", "p3", "p4"];

/**
 * First-visit card: choose a language, then read what the product does.
 *
 * Centred with a scrim rather than tucked into a corner. Once the first thing
 * it asks is "which language", it is a decision the visitor has to make before
 * the page means anything — and a language chooser that can be missed is worse
 * than none, because the visitor concludes the site is simply in the wrong
 * language. The corner-toast version was easy to overlook at exactly that
 * moment.
 *
 * The language block comes first and the copy below it re-renders in the
 * chosen language immediately, so the choice visibly does something.
 */
export function WelcomeCard() {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const { mounted, closing } = useExitAnimation(open, EXIT_MS);

  useEffect(() => {
    // localStorage throws in some privacy modes; a missing welcome card is a
    // far better failure than a landing page that does not render.
    try {
      if (localStorage.getItem(SEEN_KEY)) return;
    } catch {
      return;
    }
    const id = setTimeout(() => setOpen(true), APPEAR_DELAY_MS);
    return () => clearTimeout(id);
  }, []);

  const dismiss = () => {
    setOpen(false);
    try { localStorage.setItem(SEEN_KEY, "1"); } catch { /* nothing to do */ }
  };

  // Same mechanism as LanguageSwitcher: change the language and remember it.
  // Deliberately does NOT dismiss the card — the visitor should see the copy
  // below switch, which is what confirms the choice took effect.
  const chooseLang = (code: string) => {
    i18n.changeLanguage(code);
    try { localStorage.setItem(LANG_KEY, code); } catch { /* nothing to do */ }
  };

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") dismiss(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (!mounted) return null;

  return (
    <div
      // The scrim is the click-outside target, so no document-level listener is
      // needed — and unlike one, it cannot fire on a click that was really
      // meant for something underneath.
      className={cn(
        "fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60",
        closing ? "anim-fade-out" : "anim-fade-in"
      )}
      onClick={dismiss}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("welcome.title")}
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "w-full max-w-md bg-header border border-brand-border rounded-xs p-6",
          closing ? "anim-pop-out" : "anim-pop-in"
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <p className="label-caps text-[11px] text-brand-muted">{t("welcome.lang_label")}</p>
          <button
            onClick={dismiss}
            aria-label={t("welcome.close")}
            className="-mt-1 -mr-1 p-1 rounded-xs text-brand-muted hover:text-brand-dark transition-colors duration-200 ease-out active:translate-y-px"
          >
            <X size={14} />
          </button>
        </div>

        <div className="flex gap-2 mt-3">
          {LANGS.map(({ code, label }) => {
            const active = i18n.language === code;
            return (
              <button
                key={code}
                onClick={() => chooseLang(code)}
                aria-pressed={active}
                className={cn(
                  "flex-1 py-2 px-2 rounded-xs border text-xs transition-colors duration-200 ease-out active:translate-y-px",
                  active
                    ? "border-accent text-accent-fg bg-accent/12"
                    : "border-brand-border text-brand-muted hover:text-brand-dark hover:border-brand-muted"
                )}
              >
                {label}
              </button>
            );
          })}
        </div>

        <span className="block w-8 h-px bg-accent mt-6 mb-4" aria-hidden="true" />

        <p className="label-caps text-[11px] text-brand-muted mb-3">{t("welcome.title")}</p>
        <ul className="space-y-2.5 mb-6">
          {POINT_KEYS.map((k) => (
            <li key={k} className="flex gap-2.5 text-sm text-brand-dark leading-snug">
              <span className="mt-2 w-1 h-1 rounded-xs bg-accent shrink-0" aria-hidden="true" />
              {t(`welcome.${k}`)}
            </li>
          ))}
        </ul>

        <button
          onClick={dismiss}
          className="w-full h-9 rounded-xs border border-accent bg-transparent text-accent-fg label-caps text-xs transition-[color,background-color,border-color,transform] duration-150 ease-out hover:bg-accent/12 hover:border-accent-fg active:bg-accent/25 active:translate-y-px"
        >
          {t("welcome.ok")}
        </button>
      </div>
    </div>
  );
}
