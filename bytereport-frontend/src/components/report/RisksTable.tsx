import { useTranslation } from "react-i18next";
import type { TopRisk } from "@/types";

interface Props { risks: TopRisk[]; }

export function RisksTable({ risks }: Props) {
  const { t } = useTranslation();
  if (!risks.length) return null;
  return (
    <div>
      <h3 className="text-sm font-semibold uppercase tracking-widest text-brand-muted mb-3">
        {t("report.top_risks_title")}
      </h3>
      {/* A four-column table cannot be read at 390px; each risk becomes a
          card with its fields stacked, in the same order as the columns. */}
      <div className="md:hidden space-y-2">
        {risks.map((r, i) => (
          <div key={i} className="rounded-xs border border-brand-border bg-surface p-4">
            <div className="flex gap-3">
              <span className="mono-num text-brand-blue shrink-0">{i + 1}</span>
              <p className="text-sm font-medium text-brand-dark">{r.risk}</p>
            </div>
            <dl className="mt-3 space-y-2 pl-6 text-sm">
              <div>
                <dt className="label-caps text-[10px] text-brand-muted mb-0.5">{t("report.col_impact")}</dt>
                <dd className="text-brand-muted">{r.impact}</dd>
              </div>
              <div>
                <dt className="label-caps text-[10px] text-brand-muted mb-0.5">{t("report.col_recommendation")}</dt>
                <dd className="text-brand-muted">{r.recommendation}</dd>
              </div>
            </dl>
          </div>
        ))}
      </div>
      <div className="hidden md:block rounded-xl border border-brand-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-header text-fg text-xs">
              <th className="px-4 py-3 text-left w-6">#</th>
              <th className="px-4 py-3 text-left">{t("report.col_risk")}</th>
              <th className="px-4 py-3 text-left">{t("report.col_impact")}</th>
              <th className="px-4 py-3 text-left">{t("report.col_recommendation")}</th>
            </tr>
          </thead>
          <tbody>
            {risks.map((r, i) => (
              <tr key={i} className={i % 2 === 0 ? "bg-transparent" : "bg-ground"}>
                <td className="px-4 py-3 font-bold text-brand-blue">{i + 1}</td>
                <td className="px-4 py-3 font-medium text-brand-dark">{r.risk}</td>
                <td className="px-4 py-3 text-brand-muted">{r.impact}</td>
                <td className="px-4 py-3 text-brand-muted">{r.recommendation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
