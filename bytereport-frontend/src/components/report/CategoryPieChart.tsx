import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CHART_UI, assignCategoryColors } from "@/lib/chartTokens";
import { CHART_ANIM_MS, useReducedMotion } from "@/lib/motion";
import { useTranslation } from "react-i18next";
import { categoryLabel, formatCurrency, mergeCategoriesCI } from "@/lib/utils";
import type { CategoryBreakdown } from "@/types";

// Colours come from design-tokens.json and are assigned by category NAME, using
// the same hash the PDF uses (design_tokens.assign_category_colors), so a
// category is the same colour in both surfaces. Not by slice index: that
// repainted everything whenever shares reordered. The palette is hue-varied —
// the previous monochrome ramp blurred together past about four slices.

interface Props { data: CategoryBreakdown[]; title?: string; currency?: string; }

export function CategoryPieChart({ data, title, currency = "UZS" }: Props) {
  const { t } = useTranslation();
  // Label first, then colour by the labelled name — the PDF does the same,
  // so a category keeps its colour on both surfaces.
  // Label FIRST, then merge on the label. Merging on the raw name only is not
  // enough: "Реклама" and "marketing" are different raw strings that both
  // render as "Marketing", so the legend still showed two identical entries.
  // Anything a reader cannot tell apart must be one wedge.
  const labelled = mergeCategoriesCI(
    data.map((d) => ({ ...d, category: categoryLabel(d.category, t) }))
  );
  const sliceColors = assignCategoryColors(labelled.map((d) => d.category));
  const reduced = useReducedMotion();

  return (
    <Card>
      <CardHeader>
        {/* No caller passes a title; the default used to be a Russian literal. */}
        <CardTitle>{title ?? t("report.categories_title")}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={280}>
          <PieChart>
            <Pie
              data={labelled} dataKey="total" nameKey="category"
              cx="50%" cy="50%" outerRadius={90} innerRadius={50}
              paddingAngle={2}
              isAnimationActive={!reduced}
              animationDuration={CHART_ANIM_MS}
              animationEasing="ease-out"
            >
              {labelled.map((_, i) => (
                // stroke defaults to white in recharts, which drew bright
                // hairlines between wedges on the dark ground.
                <Cell key={i} fill={sliceColors[i]} stroke={CHART_UI.tooltipBg} strokeWidth={2} />
              ))}
            </Pie>
            <Tooltip
              formatter={(v: number) => formatCurrency(v, currency)}
              contentStyle={{ borderRadius: 3, background: CHART_UI.tooltipBg, color: CHART_UI.text, border: `1px solid ${CHART_UI.tooltipBorder}`, fontSize: 12 }}
            />
            <Legend
              iconType="circle" iconSize={8}
              formatter={(v) => <span style={{ fontSize: 11, color: CHART_UI.axis }}>{v}</span>}
            />
          </PieChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
