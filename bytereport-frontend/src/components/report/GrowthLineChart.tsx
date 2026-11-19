import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, ReferenceLine,
} from "recharts";
import { useTranslation } from "react-i18next";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CHART_UI, SERIES } from "@/lib/chartTokens";
import { CHART_ANIM_MS, CHART_STAGGER_MS, useReducedMotion } from "@/lib/motion";
import { formatPercent } from "@/lib/utils";
import type { MoMGrowth, MoMOutlier } from "@/types";

interface Props {
  data: MoMGrowth[];
  /** Points the backend withheld from the line (near-zero base). */
  outliers?: MoMOutlier[];
}

const METRIC_KEY: Record<string, string> = {
  revenue: "report.revenue",
  expenses: "report.expenses",
  profit: "report.profit",
};

function fmtAmount(v: number): string {
  return Math.round(v).toLocaleString("ru-RU").replace(/ /g, " ");
}

export function GrowthLineChart({ data, outliers = [] }: Props) {
  const { t } = useTranslation();
  // Both hooks run before the early return below — the empty-data case must not
  // change how many hooks this component calls.
  const reduced = useReducedMotion();
  const anim = (i: number) => ({
    isAnimationActive: !reduced,
    animationDuration: CHART_ANIM_MS,
    animationBegin: i * CHART_STAGGER_MS,
    animationEasing: "ease-out" as const,
  });
  if (data.length === 0) return null;

  // Plot the *_display values: the backend (growth_display.py) has already
  // removed percentages taken from a near-zero base, which would otherwise
  // stretch the axis by orders of magnitude and flatten every real trend.
  // Fall back to the raw field for reports saved before those fields existed.
  const points = data.map((d) => ({
    ...d,
    revenue_plot: d.revenue_growth_display !== undefined ? d.revenue_growth_display : d.revenue_growth_pct,
    expense_plot: d.expense_growth_display !== undefined ? d.expense_growth_display : d.expense_growth_pct,
    profit_plot:  d.profit_growth_display  !== undefined ? d.profit_growth_display  : d.profit_growth_pct,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("report.growth_chart_title")}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={points} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_UI.grid} vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 12, fill: CHART_UI.axis }} />
            <YAxis tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11, fill: CHART_UI.axis }} width={44} />
            <ReferenceLine y={0} stroke={CHART_UI.grid} />
            <Tooltip
              formatter={(v: number) => formatPercent(v)}
              contentStyle={{ borderRadius: 3, background: CHART_UI.tooltipBg, color: CHART_UI.text, border: `1px solid ${CHART_UI.tooltipBorder}`, fontSize: 12 }}
            />
            <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
            {/* connectNulls is off on purpose: a withheld point must leave a
                visible gap rather than be bridged as if it were measured. */}
            <Line
              type="monotone" dataKey="revenue_plot" name={t("report.revenue")}
              stroke={SERIES.revenue} strokeWidth={2} dot={{ r: 4 }} connectNulls={false} {...anim(0)}
            />
            <Line
              type="monotone" dataKey="expense_plot" name={t("report.expenses")}
              stroke={SERIES.expenses} strokeWidth={2} dot={{ r: 4 }} connectNulls={false} {...anim(1)}
            />
            <Line
              type="monotone" dataKey="profit_plot" name={t("report.profit")}
              stroke={SERIES.profit} strokeWidth={2} dot={{ r: 4 }} connectNulls={false} {...anim(2)}
            />
          </LineChart>
        </ResponsiveContainer>

        {outliers.length > 0 && (
          <ul className="mt-3 space-y-1">
            {outliers.map((o, i) => (
              <li key={i} className="text-xs text-brand-muted leading-relaxed">
                {t("report.growth_outlier", {
                  month: o.month,
                  metric: t(METRIC_KEY[o.metric] ?? "report.revenue"),
                  previous: fmtAmount(o.previous),
                  current: fmtAmount(o.current),
                })}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
