import { useTranslation } from "react-i18next";
import type { PriorityAction } from "@/types";

interface Props { actions: PriorityAction[]; }

export function PriorityActions({ actions }: Props) {
  const { t } = useTranslation();
  if (!actions.length) return null;
  const sorted = [...actions].sort((a, b) => a.priority - b.priority);
  return (
    <div>
      <h3 className="text-sm font-semibold uppercase tracking-widest text-brand-muted mb-3">
        {t("report.priority_actions_title")}
      </h3>
      <div className="space-y-3">
        {sorted.map((a) => (
          <div key={a.priority} className="flex gap-4 rounded-xl bg-surface border border-brand-border p-4">
            <div className="w-10 h-10 rounded-full bg-line/40 flex items-center justify-center shrink-0">
              <span className="text-brand-blue font-extrabold text-lg tabular">{a.priority}</span>
            </div>
            <div>
              <p className="text-sm font-semibold text-brand-dark">{a.action}</p>
              <p className="text-xs text-brand-muted mt-0.5">
                {t("report.expected_result")}: {a.expected_result}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
