import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, Download } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  onDownloadSample: () => void;
}

/**
 * "How do I get this file?" — the first question of anyone who has never
 * exported a statement. Collapsed by default so it costs a returning user one
 * line. The steps are deliberately general (1C, a bank's client portal): the
 * exact menus differ per bank and per 1C configuration, and a wrong menu path
 * is worse than a general one.
 */
export function ExportHelp({ onDownloadSample }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const steps = (key: string) => t(key, { returnObjects: true }) as string[];

  return (
    <div className="border border-brand-border rounded-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="export-help"
        className="w-full flex items-center justify-between gap-3 px-4 min-h-11 py-2.5 text-left text-sm text-brand-dark hover:text-accent-fg transition-colors duration-200 ease-out"
      >
        {t("upload.help_title")}
        <ChevronDown size={16} className={cn("shrink-0 text-brand-muted transition-transform duration-200 ease-out", open && "rotate-180")} />
      </button>

      {open && (
        <div id="export-help" className="px-4 pb-4 pt-1 border-t border-brand-border anim-fade-in">
          <div className="grid gap-5 sm:grid-cols-2 mt-3">
            {(["1c", "bank"] as const).map((src) => (
              <div key={src}>
                <p className="label-caps text-[11px] text-brand-muted mb-2">{t(`upload.help_${src}_title`)}</p>
                <ol className="space-y-1.5 text-xs text-brand-dark leading-relaxed list-decimal pl-4">
                  {steps(`upload.help_${src}_steps`).map((s, i) => <li key={i}>{s}</li>)}
                </ol>
              </div>
            ))}
          </div>
          <p className="text-xs text-brand-muted leading-relaxed mt-4">{t("upload.help_requirements")}</p>
          <button
            type="button"
            onClick={onDownloadSample}
            className="mt-3 inline-flex items-center gap-1.5 min-h-11 text-xs text-accent-fg hover:text-brand-dark transition-colors duration-200 ease-out"
          >
            <Download size={13} />
            {t("upload.download_sample")}
          </button>
        </div>
      )}
    </div>
  );
}
