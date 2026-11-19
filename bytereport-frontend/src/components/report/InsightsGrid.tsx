import { useTranslation } from "react-i18next";
import { cn, severityBg } from "@/lib/utils";
import { SeverityBadge } from "@/components/ui/SeverityBadge";
import type { KeyInsight } from "@/types";

interface Props { insights: KeyInsight[]; }

export function InsightsGrid({ insights }: Props) {
  const { t } = useTranslation();
  if (!insights.length) return null;
  return (
    <div>
      <h3 className="text-sm font-semibold uppercase tracking-widest text-brand-muted mb-3">
        {t("report.key_insights")}
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {insights.map((ins, i) => (
          <div key={i} className={cn("rounded-xl border p-4", severityBg(ins.severity))}>
            <div className="flex items-start justify-between gap-2 mb-2">
              <span className="text-xs font-semibold text-brand-dark leading-snug">{ins.title}</span>
              <SeverityBadge severity={ins.severity} />
            </div>
            <p className="text-xs text-brand-muted leading-relaxed">{ins.explanation}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
