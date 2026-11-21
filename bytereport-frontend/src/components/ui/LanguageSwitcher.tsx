import { useState, useRef, useEffect } from "react";
import { Globe, ChevronDown, Check } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { useExitAnimation } from "@/lib/motion";

const LANGS = [
  { code: "uz", label: "O'zbekcha" },
  { code: "ru", label: "Русский" },
  { code: "en", label: "English" },
];

interface Props {
  /** "dark" renders on a dark background (e.g. inside a dark panel) */
  variant?: "light" | "dark";
}

export function LanguageSwitcher({ variant = "light" }: Props) {
  const { i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const { mounted, closing } = useExitAnimation(open, 150);
  const ref = useRef<HTMLDivElement>(null);

  const current = LANGS.find((l) => l.code === i18n.language) ?? LANGS[1];

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const switchLang = (code: string) => {
    i18n.changeLanguage(code);
    localStorage.setItem("br_lang", code);
    setOpen(false);
  };

  const isDark = variant === "dark";

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex items-center gap-1.5 px-3 py-1.5 max-md:min-h-11 max-md:px-2.5 rounded-lg text-sm font-medium transition-all select-none",
          isDark
            ? "text-fg/70 hover:text-fg hover:bg-transparent/10 border border-transparent hover:border-line-strong"
            : "text-brand-muted hover:text-brand-dark hover:bg-ground border border-transparent hover:border-brand-border"
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={current.label}
      >
        <Globe size={14} className="shrink-0" />
        {/* The full name costs ~80px a phone header does not have. */}
        <span className="hidden sm:inline">{current.label}</span>
        <span className="sm:hidden uppercase">{current.code}</span>
        <ChevronDown
          size={12}
          className={cn("shrink-0 transition-transform duration-150", open && "rotate-180")}
        />
      </button>

      {mounted && (
        <div
          role="listbox"
          // Solid bg-header: a dropdown is an overlay. The redesign swept
          // bg-white -> bg-transparent everywhere, which is right for cards
          // sitting on the page ground and wrong for anything floating.
          // origin-top-right: the panel grows out of the button it hangs
          // from. Scaling from the centre would make it drift sideways.
          className={cn(
            "absolute right-0 top-full mt-1.5 w-44 bg-header border border-brand-border rounded-xs py-1 z-50 origin-top-right",
            closing ? "anim-pop-out" : "anim-pop-in"
          )}
        >
          {LANGS.map((lang) => {
            const active = lang.code === i18n.language;
            return (
              <button
                key={lang.code}
                role="option"
                aria-selected={active}
                onClick={() => switchLang(lang.code)}
                className={cn(
                  "max-md:min-h-11 w-full flex items-center justify-between px-3 py-2 text-sm transition-colors",
                  active
                    ? "text-brand-blue font-semibold bg-ground"
                    : "text-brand-dark hover:bg-ground"
                )}
              >
                <span>{lang.label}</span>
                {active && <Check size={13} className="text-brand-blue shrink-0" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
