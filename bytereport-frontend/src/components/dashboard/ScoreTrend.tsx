import { useTranslation } from "react-i18next";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { CHART_UI } from "@/lib/chartTokens";
import { scoreColor } from "@/lib/utils";
import { useReducedMotion } from "@/lib/motion";
import type { ReportSummary } from "@/types";

/** Same business, ignoring case and stray spaces ("Кофейня " == "кофейня"). */
export function sameBusiness(a: ReportSummary, b: ReportSummary): boolean {
  const norm = (s: string) => s.trim().replace(/\s+/g, " ").toLowerCase();
  return norm(a.business_name) === norm(b.business_name);
}

/**
 * Score change against the previous report OF THE SAME BUSINESS, or null.
 * `history` is newest first. Comparing an accountant's two different clients
 * would produce a number that means nothing, so it is not produced.
 */
export function deltaToPrevious(history: ReportSummary[], index: number): number | null {
  const current = history[index];
  const previous = history.slice(index + 1).find((r) => sameBusiness(r, current));
  return previous ? current.score - previous.score : null;
}

export function DeltaLabel({ delta, long = false }: { delta: number; long?: boolean }) {
  const { t } = useTranslation();
  const Icon = delta > 0 ? TrendingUp : delta < 0 ? TrendingDown : Minus;
  const text = delta === 0
    ? (long ? t("dashboard.trend_same") : "±0")
    : `${delta > 0 ? "+" : "−"}${Math.abs(delta)}`;
  return (
    <span className="inline-flex items-center gap-1 text-xs text-brand-muted mono-num">
      <Icon size={13} className="shrink-0" />
      {long && delta !== 0 ? t("dashboard.trend_delta", { delta: text }) : text}
    </span>
  );
}

/**
 * Health Score over time, one point per saved report. Shown from the second
 * report on; a single point is not a trend.
 */
export function ScoreTrend({ history }: { history: ReportSummary[] }) {
  const { t, i18n } = useTranslation();
  // Recharts animates on its own clock and ignores the media query.
  const reduced = useReducedMotion();
  if (history.length < 2) return null;
  const locale = i18n.language === "en" ? "en-US" : "ru-RU";
  const data = [...history].reverse().map((r) => ({
    date: new Date(r.created_at).toLocaleDateString(locale, { day: "numeric", month: "short" }),
    score: r.score,
    name: r.business_name,
  }));
  const delta = deltaToPrevious(history, 0);

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 mb-4">
          <p className="label-caps text-xs text-brand-muted">{t("dashboard.trend_title")}</p>
          {delta !== null && <DeltaLabel delta={delta} long />}
        </div>
        <ResponsiveContainer width="100%" height={160}>
          <LineChart data={data} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
            {/* Grid lines at the zone boundaries, so a point's zone reads
                off the chart without a legend. */}
            <CartesianGrid stroke={CHART_UI.grid} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: CHART_UI.axis }} tickLine={false} />
            <YAxis
              domain={[0, 100]} ticks={[0, 40, 55, 70, 100]}
              tick={{ fontSize: 11, fill: CHART_UI.axis }} tickLine={false} axisLine={false}
            />
            <Tooltip
              formatter={(v: number) => [v, t("report.health_score_title")]}
              labelFormatter={(_l, payload) => {
                const p = payload?.[0]?.payload as { name?: string; date?: string } | undefined;
                return p ? `${p.name} · ${p.date}` : "";
              }}
              contentStyle={{
                borderRadius: 3, background: CHART_UI.tooltipBg, color: CHART_UI.text,
                border: `1px solid ${CHART_UI.tooltipBorder}`, fontSize: 12,
              }}
            />
            <Line
              type="monotone" dataKey="score" stroke={CHART_UI.accent} strokeWidth={2}
              dot={(props: { cx?: number; cy?: number; payload?: { score: number }; index?: number }) => (
                <circle
                  key={props.index} cx={props.cx} cy={props.cy} r={4}
                  fill={scoreColor(props.payload?.score ?? 0)} stroke="none"
                />
              )}
              activeDot={{ r: 5 }}
              isAnimationActive={!reduced}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
