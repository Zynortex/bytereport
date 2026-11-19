/**
 * Chart colours, imported from the repo-root design-tokens.json.
 *
 * The PDF pipeline reads the same file (app/services/design_tokens.py), so the
 * dashboard and the printed report cannot drift apart. Nothing here is a
 * hand-copied hex — if a colour needs to change, change it in the JSON.
 */
import tokens from "../../../design-tokens.json";

/** Dark → light ramp for categorical charts. Slices are sorted by descending share. */
export const CHART_RAMP: string[] = tokens.charts.ramp;

/** Three-series charts: revenue / expenses / profit. */
export const SERIES = {
  revenue: tokens.charts.series.revenue,
  expenses: tokens.charts.series.expenses,
  profit: tokens.charts.series.profit,
} as const;

/** Cash-gap forecast — muted terracotta, a risk signal that does not shout. */
export const CASH_GAP: string = tokens.charts.cash_gap;

/** Chart furniture on the dark ground. */
export const CHART_UI = {
  grid: tokens.theme.border_default,
  axis: tokens.theme.text_muted,
  tooltipBg: tokens.theme.bg_header,
  tooltipBorder: tokens.theme.border_default,
  text: tokens.theme.text_primary,
  accent: tokens.theme.accent,
} as const;

/**
 * Health Score zones, critical → excellent.
 * The PDF reads the same entry (pdf_generator._ZONE_COLORS), so the two cannot
 * drift — they used to be two independent hardcoded copies.
 */
export const ZONES = {
  critical: tokens.zones.critical,
  unstable: tokens.zones.unstable,
  stable: tokens.zones.stable,
  excellent: tokens.zones.excellent,
} as const;

/** Muted severity scale — the only place a semantic hue is used. */
export const SEVERITY = {
  high: tokens.severity.high,
  medium: tokens.severity.medium,
  low: tokens.severity.low,
} as const;

/**
 * Hue-varied palette for categorical charts (expense donut).
 * The monochrome ramp is kept for genuinely ordinal data; category slices need
 * distinguishable hues, not just lightness steps.
 */
export const CATEGORY_COLORS: readonly string[] = tokens.charts.categories;

/** Names meaning "everything else" — always take the reserved neutral grey. */
const OTHER_NAMES = new Set(["прочее", "other", "бошқа", "прочие", "остальное"]);

/**
 * Preferred palette slot for a category name.
 * Must stay byte-identical to design_tokens.category_color_index in Python so
 * the web donut and the PDF donut colour a category the same way.
 */
export function categoryColorIndex(name: string, slots: number): number {
  let h = 0;
  for (const ch of name.trim().toLowerCase()) {
    h = (h * 31 + ch.codePointAt(0)!) % 4294967296;
  }
  return h % slots;
}

/**
 * Colour per category, stable by name rather than by sort position — so a
 * category keeps its colour between reports even when shares reorder.
 * Collisions probe upward, so no two slices in one chart ever match.
 */
export function assignCategoryColors(names: string[]): string[] {
  const palette = CATEGORY_COLORS;
  if (palette.length === 0) return [];
  const hued = palette.slice(0, -1);
  const neutral = palette[palette.length - 1];

  const taken = new Set<number>();
  return names.map((name) => {
    if (OTHER_NAMES.has(name.trim().toLowerCase())) return neutral;
    let probe = categoryColorIndex(name, hued.length);
    while (taken.has(probe) && taken.size < hued.length) {
      probe = (probe + 1) % hued.length;
    }
    taken.add(probe);
    return hued[probe];
  });
}
