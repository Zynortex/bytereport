import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AreaChart, Area, BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from "recharts";
import { AlertTriangle, CheckCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CASH_GAP, CHART_UI } from "@/lib/chartTokens";
import { formatCompact, formatCurrency } from "@/lib/utils";
import { api } from "@/api/endpoints";
import { parseApiError } from "@/api/client";
import { useReducedMotion } from "@/lib/motion";
import type { CashflowForecast, FinancialMetrics } from "@/types";

interface Props {
  metrics: FinancialMetrics;
  currency: string;
  /** Called with the recomputed forecast after the user enters a balance. */
  onForecast: (forecast: CashflowForecast) => void;
}

const CONFIDENCE_BADGE: Record<string, string> = {
  HIGH:   "bg-transparent text-fg-subtle border border-line",
  MEDIUM: "bg-transparent text-sev-medium border border-sev-medium/60",
  LOW:    "bg-transparent text-brand-muted border border-line",
};



/** "12 500 000" / "-300 000" / "1,5" → number, or null when it is not one. */
export function parseAmount(raw: string): number | null {
  const cleaned = raw.replace(/[\s\u00a0\u202f]/g, "").replace(/[\u2212\u2013]/g, "-").replace(",", ".");
  if (!cleaned || !/^-?\d+(\.\d+)?$/.test(cleaned)) return null;
  return Number(cleaned);
}

/**
 * The cash forecast, saying only what the data supports.
 *
 * With the account balance at the end of the period it is a BALANCE forecast:
 * a line from that balance, and a dated warning if it crosses zero. Without
 * it there is no starting point, so it is a TREND of weekly net flow — bars,
 * no date, no amount — with the reason stated and a field to add the balance
 * right here. Recomputing is arithmetic only (no AI), so adding the balance
 * never costs a second report. Same title and note as the PDF, from
 * report-copy.json.
 */
export function CashForecastCard({ metrics, currency, onForecast }: Props) {
  const { t, i18n } = useTranslation();
  const cf = metrics.cashflow_forecast;
  const inputRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reduced = useReducedMotion();

  if (!cf) return null;
  const known = !!cf.balance_known;
  const locale = i18n.language === "en" ? "en-US" : "ru-RU";
  const shortMoney = (v: number) => formatCompact(v, i18n.language);
  const weekTick = (v: number) => t("report.week_label", { n: v });
  const tooltipStyle = {
    borderRadius: 3, background: CHART_UI.tooltipBg, color: CHART_UI.text,
    border: `1px solid ${CHART_UI.tooltipBorder}`, fontSize: 12,
  };

  const recompute = async () => {
    const balance = parseAmount(value);
    if (balance === null) {
      setError(t("cash.balance_invalid"));
      inputRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onForecast(await api.recomputeForecast(metrics, balance));
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const riskDate = cf.risk_date
    ? new Date(cf.risk_date).toLocaleDateString(locale, { day: "numeric", month: "long", year: "numeric" })
    : null;
  const color = known && cf.has_risk ? CASH_GAP : CHART_UI.accent;
  const netData = cf.weekly_projection.map((w) => ({
    week: w.week,
    net: w.projected_net ?? (w.projected_revenue ?? 0) - (w.projected_expenses ?? 0),
  }));

  return (
    <Card className={known && cf.has_risk ? "border-sev-high/40" : "border-line"}>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between gap-3 mb-4">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-brand-muted">
            {known ? t("cash_forecast.title_balance") : t("cash_forecast.title_trend")}
          </h3>
          <span className={`inline-flex shrink-0 items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${CONFIDENCE_BADGE[cf.confidence]}`}>
            {t("report.confidence_label")}: {t(`report.confidence_${cf.confidence.toLowerCase()}`)}
          </span>
        </div>

        {known ? (
          <>
            {cf.has_risk ? (
              <div className="flex items-start gap-3 bg-sev-high/15 border border-sev-high/40 rounded-xl px-4 py-3 mb-3">
                <AlertTriangle size={16} className="text-sev-high shrink-0 mt-0.5" />
                <p className="text-sm text-sev-high font-medium leading-relaxed">
                  {t("report.cashflow_risk_prefix")}
                  {riskDate ? ` ${riskDate}` : ""}
                  {cf.risk_amount != null ? ` — ${formatCurrency(cf.risk_amount, currency)}` : ""}
                  {t("report.cashflow_risk_suffix")}
                </p>
              </div>
            ) : (
              <div className="flex items-center gap-3 bg-line/40 border border-line rounded-xl px-4 py-3 mb-3">
                <CheckCircle size={16} className="text-fg-subtle shrink-0" />
                <p className="text-sm text-fg-subtle font-medium">{t("report.cashflow_ok")}</p>
              </div>
            )}
            <p className="text-xs text-brand-muted mb-4">
              {t("cash_forecast.from_balance").replace("{amount}", formatCurrency(cf.closing_balance ?? 0, currency))}
            </p>

            {cf.weekly_projection.length > 0 && (
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={cf.weekly_projection} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="cfGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={color} stopOpacity={0.18} />
                      <stop offset="95%" stopColor={color} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_UI.grid} />
                  <XAxis dataKey="week" tickFormatter={weekTick} tick={{ fontSize: 11, fill: CHART_UI.axis }} />
                  <YAxis tick={{ fontSize: 11, fill: CHART_UI.axis }} tickFormatter={shortMoney} width={48} />
                  <Tooltip
                    formatter={(v: number) => [formatCurrency(v, currency), t("report.balance_forecast")]}
                    labelFormatter={(label: number) => t("report.week_full", { n: label })}
                    contentStyle={tooltipStyle}
                  />
                  <ReferenceLine y={0} stroke={CASH_GAP} strokeDasharray="4 3" strokeWidth={1.5} />
                  <Area
                    type="monotone" dataKey="projected_balance" stroke={color} strokeWidth={2.5}
                    fill="url(#cfGradient)" dot={{ fill: color, r: 4, strokeWidth: 0 }} activeDot={{ r: 5 }}
                    isAnimationActive={!reduced}
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </>
        ) : (
          <>
            <p className="text-sm text-brand-muted leading-relaxed mb-4 max-w-3xl">
              {t("cash_forecast.needs_balance")}{" "}
              <button
                type="button"
                onClick={() => inputRef.current?.focus()}
                className="text-brand-blue underline underline-offset-2 hover:text-brand-dark transition-colors duration-200 ease-out"
              >
                {t("cash_forecast.needs_balance_action")}
              </button>
            </p>

            {netData.length > 0 && (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={netData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_UI.grid} vertical={false} />
                  <XAxis dataKey="week" tickFormatter={weekTick} tick={{ fontSize: 11, fill: CHART_UI.axis }} />
                  <YAxis tick={{ fontSize: 11, fill: CHART_UI.axis }} tickFormatter={shortMoney} width={48} />
                  <Tooltip
                    formatter={(v: number) => [formatCurrency(v, currency), t("cash.net_flow")]}
                    labelFormatter={(label: number) => t("report.week_full", { n: label })}
                    contentStyle={tooltipStyle}
                    cursor={{ fill: CHART_UI.grid, opacity: 0.3 }}
                  />
                  <ReferenceLine y={0} stroke={CHART_UI.axis} strokeWidth={1} />
                  <Bar dataKey="net" radius={[2, 2, 0, 0]} maxBarSize={44} isAnimationActive={!reduced}>
                    {netData.map((d) => (
                      <Cell key={d.week} fill={d.net >= 0 ? CHART_UI.accent : CASH_GAP} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}

            <div className="mt-5 pt-4 border-t border-line flex flex-col sm:flex-row sm:items-end gap-3">
              <label className="flex-1 min-w-0">
                <span className="block text-xs font-medium text-brand-dark mb-1.5">
                  {t("cash.balance_label")} ({currency})
                </span>
                <input
                  ref={inputRef}
                  inputMode="decimal"
                  value={value}
                  onChange={(e) => { setValue(e.target.value); setError(null); }}
                  onKeyDown={(e) => { if (e.key === "Enter") recompute(); }}
                  placeholder={t("cash.balance_placeholder")}
                  className="w-full rounded-xs border border-brand-border bg-transparent px-3 py-2 max-md:min-h-11 text-sm text-brand-dark mono-num placeholder:text-fg-subtle transition-[border-color] duration-200 ease-out focus:outline-none focus:border-accent-fg focus:ring-2 focus:ring-accent/30"
                />
              </label>
              <Button onClick={recompute} loading={busy} disabled={!value.trim()} className="sm:w-auto">
                {t("cash.recompute")}
              </Button>
            </div>
            <p className="text-xs text-brand-muted mt-2">{t("cash.recompute_free")}</p>
            {error && <p className="text-xs text-danger mt-1.5">{error}</p>}
          </>
        )}
      </CardContent>
    </Card>
  );
}
