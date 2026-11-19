import { useTranslation } from "react-i18next";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CHART_UI, SERIES } from "@/lib/chartTokens";
import { CHART_ANIM_MS, CHART_STAGGER_MS, useReducedMotion } from "@/lib/motion";
import { formatCompact, formatCurrency } from "@/lib/utils";
import type { MonthMetrics } from "@/types";

interface Props { data: MonthMetrics[]; currency?: string; }

export function MonthlyChart({ data, currency = "UZS" }: Props) {
  const { t, i18n } = useTranslation();
  // Axis shorthand in the interface language — it was fixed to ru-RU, so an
  // English report read "650 тыс." on the axis.
  const fmt = (v: number) => formatCompact(v, i18n.language);
  // recharts animates in JS, so the reduced-motion setting has to be passed
  // in explicitly — the CSS media query cannot reach it.
  const reduced = useReducedMotion();
  const anim = (i: number) => ({
    isAnimationActive: !reduced,
    animationDuration: CHART_ANIM_MS,
    animationBegin: i * CHART_STAGGER_MS,
    animationEasing: "ease-out" as const,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("report.monthly_chart_title")}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_UI.grid} vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 12, fill: CHART_UI.axis }} />
            <YAxis tickFormatter={fmt} tick={{ fontSize: 11, fill: CHART_UI.axis }} width={52} />
            <Tooltip
              formatter={(v: number) => formatCurrency(v, currency)}
              contentStyle={{ borderRadius: 3, background: CHART_UI.tooltipBg, color: CHART_UI.text, border: `1px solid ${CHART_UI.tooltipBorder}`, fontSize: 12 }}
            />
            <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="revenue"  name={t("report.revenue")}  fill={SERIES.revenue} radius={[1, 1, 0, 0]} {...anim(0)} />
            <Bar dataKey="expenses" name={t("report.expenses")}  fill={SERIES.expenses} radius={[1, 1, 0, 0]} {...anim(1)} />
            <Bar dataKey="profit"   name={t("report.profit")}  fill={SERIES.profit} radius={[1, 1, 0, 0]} {...anim(2)} />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
