import { useTranslation } from "react-i18next";
import { categoryLabel, cn, severityBg } from "@/lib/utils";
import { SeverityBadge } from "@/components/ui/SeverityBadge";
import type { AnomalyReport } from "@/types";

interface Props { anomalies: AnomalyReport[]; }

export function AnomaliesTable({ anomalies }: Props) {
  const { t } = useTranslation();
  if (!anomalies.length) return null;
  return (
    <div>
      <h3 className="text-sm font-semibold uppercase tracking-widest text-brand-muted mb-3">
        {t("report.anomalies_title")}
      </h3>
      <div className="space-y-2">
        {anomalies.map((a, i) => (
          <div key={i} className={cn("flex flex-col sm:flex-row gap-3 sm:gap-4 rounded-xl border p-4", severityBg(a.severity))}>
            <div className="flex flex-row sm:flex-col items-center sm:items-start gap-2 sm:gap-1.5 sm:min-w-[72px]">
              <SeverityBadge severity={a.severity} />
              <span className="text-xs text-brand-muted">{categoryLabel(a.category, t)}</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-brand-dark mb-0.5">{a.issue}</p>
              <p className="text-xs text-brand-muted leading-relaxed">{a.explanation}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
