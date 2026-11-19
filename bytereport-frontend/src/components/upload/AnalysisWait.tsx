import { useTranslation } from "react-i18next";
import { CheckCircle, Loader2, AlertCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { formatCurrency } from "@/lib/utils";
import type { FinancialMetrics } from "@/types";

export interface WaitStep { label: string; done: boolean; active: boolean; }

interface Props {
  steps: WaitStep[];
  /** Seconds since the run started. */
  elapsed: number;
  /** Seconds since the AI step started, or null before it has. */
  aiElapsed: number | null;
  /** Figures computed from the file before the AI call — real, not a preview. */
  metrics: FinancialMetrics | null;
  currency: string;
  failed: boolean;
}

// The AI call's observed range. Used only to phrase the estimate; the clock
// itself is the real elapsed time.
const AI_TYPICAL_MIN = 30;
const AI_TYPICAL_MAX = 45;

/**
 * The longest moment in the product, and the one where people decide to wait
 * or close the tab. Everything here is true: the steps are the requests
 * actually in flight, the clock is wall time, the estimate is the AI call's
 * usual range counted down from when that call started (and says so plainly
 * when it runs long), and the figures are the user's own, already computed.
 * There is no percentage — nothing measures one.
 */
export function AnalysisWait({ steps, elapsed, aiElapsed, metrics, currency, failed }: Props) {
  const { t } = useTranslation();

  let estimate: string;
  if (aiElapsed === null) {
    estimate = t("upload.wait_estimate_total");
  } else if (aiElapsed < AI_TYPICAL_MAX) {
    const lo = Math.max(0, AI_TYPICAL_MIN - aiElapsed);
    const hi = AI_TYPICAL_MAX - aiElapsed;
    estimate = lo > 0
      ? t("upload.wait_remaining_range", { lo, hi })
      : t("upload.wait_remaining_upto", { hi });
  } else {
    estimate = t("upload.wait_long");
  }

  const profit = metrics ? metrics.total_revenue - metrics.total_expenses : 0;

  return (
    <div className="space-y-4">
      {!failed && (
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <p className="text-sm text-brand-muted">
            {t("upload.wait_elapsed")}{" "}
            <span className="mono-num text-brand-dark">{t("upload.wait_seconds", { n: elapsed })}</span>
          </p>
          <p className="text-xs text-brand-muted">{estimate}</p>
        </div>
      )}

      <Card>
        <CardContent className="pt-6 space-y-4">
          {steps.map((s, i) => (
            <div key={i} className="flex items-center gap-3 text-sm">
              {s.done ? (
                <CheckCircle size={16} className="text-fg-subtle shrink-0" />
              ) : s.active && !failed ? (
                <Loader2 size={16} className="text-brand-blue animate-spin shrink-0" />
              ) : s.active && failed ? (
                <AlertCircle size={16} className="text-danger shrink-0" />
              ) : (
                <div className="w-4 h-4 rounded-full border-2 border-brand-border shrink-0" />
              )}
              <span className={
                s.done ? "text-brand-dark" :
                s.active && failed ? "text-danger font-medium" :
                s.active ? "text-brand-blue font-medium" :
                "text-brand-muted"
              }>
                {s.label}
              </span>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Already true while the AI is still thinking: the user's own figures. */}
      {metrics && (
        <Card className="anim-fade-up">
          <CardContent className="pt-6">
            <p className="label-caps text-[11px] text-brand-muted mb-4">{t("upload.wait_computed")}</p>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-4 text-left">
              {[
                ["upload.wait_revenue", formatCurrency(metrics.total_revenue, currency)],
                ["upload.wait_expenses", formatCurrency(metrics.total_expenses, currency)],
                ["upload.wait_profit", formatCurrency(profit, currency)],
                ["upload.wait_count", String(metrics.transaction_count)],
              ].map(([key, value]) => (
                <div key={key} className="min-w-0">
                  <dt className="text-xs text-brand-muted mb-0.5">{t(key)}</dt>
                  <dd className={`mono-num text-base sm:text-lg break-words ${
                    key === "upload.wait_profit" && profit < 0 ? "text-sev-high-fg" : "text-brand-dark"
                  }`}>
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="text-xs text-brand-muted mt-4">
              {t("upload.wait_period", { from: metrics.period_start, to: metrics.period_end })}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
