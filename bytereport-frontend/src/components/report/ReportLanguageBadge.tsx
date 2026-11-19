import { useTranslation } from "react-i18next";
import { Languages } from "lucide-react";

/**
 * Shown only when the report text and the interface are in different
 * languages, so an English report under a Russian interface reads as a
 * choice that was made, not as a bug.
 */
export function ReportLanguageBadge({ language }: { language?: string }) {
  const { t, i18n } = useTranslation();
  const ui = (i18n.language || "en").slice(0, 2);
  if (!language || language === ui) return null;
  return (
    <span className="inline-flex items-center gap-1.5 border border-brand-border rounded-xs px-2 py-0.5 text-[11px] text-brand-muted">
      <Languages size={12} className="shrink-0" />
      {t("report.language_badge", { language: t(`report.language_name_${language}`) })}
    </span>
  );
}
