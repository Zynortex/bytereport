import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { ZONES } from "./chartTokens";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number, currency = "UZS"): string {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

/** The Intl locale for an interface language (Uzbek is written in Cyrillic here). */
export function numberLocale(lang: string | undefined): string {
  const code = (lang || "ru").slice(0, 2);
  return code === "en" ? "en-US" : code === "uz" ? "uz-Cyrl-UZ" : "ru-RU";
}

/** Chart-axis shorthand in the interface language: 1,3 млн / 1.3M / 1,3млн. */
export function formatCompact(value: number, lang: string | undefined): string {
  return new Intl.NumberFormat(numberLocale(lang), { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function formatPercent(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

// Severity styling for insight/anomaly cards.
//
// These lived on light-theme Tailwind classes (bg-red-50 / border-red-200) and
// survived the redesign audit because that audit only scanned .tsx — this is a
// .ts file. On the dark ground the fills stayed pale while the text turned
// light, so titles were nearly invisible.
//
// Now consistent with the rest of the language: no fill, a hairline in the
// severity hue, and a very low-alpha tint of the same hue.
export function severityColor(severity: string): string {
  return {
    high: "text-sev-high-fg",
    medium: "text-sev-medium-fg",
    low: "text-sev-low-fg",
  }[severity] ?? "text-brand-muted";
}

export function severityBg(severity: string): string {
  return {
    high: "border-sev-high/60 bg-sev-high/10",
    medium: "border-sev-medium/60 bg-sev-medium/10",
    low: "border-sev-low/60 bg-sev-low/10",
  }[severity] ?? "border-brand-border bg-transparent";
}

// 4 zones matching backend score_to_status_key(): 0-39 critical, 40-54 unstable,
// 55-69 stable, 70+ excellent. Boundaries must stay in sync with financial_engine.py.
export function scoreColor(score: number): string {
  // Colours come from design-tokens.json via chartTokens, the same entry the
  // PDF reads. Previously this was a second hardcoded copy of the zone palette.
  if (score >= 70) return ZONES.excellent;
  if (score >= 55) return ZONES.stable;
  if (score >= 40) return ZONES.unstable;
  return ZONES.critical;
}

// Returns the i18n key suffix for the zone label (use with t("report.zone_" + key)).
export function scoreZoneKey(score: number): "critical" | "unstable" | "stable" | "strong" {
  if (score >= 70) return "strong";
  if (score >= 55) return "stable";
  if (score >= 40) return "unstable";
  return "critical";
}


/**
 * A controlled-vocabulary token becomes a label; prose is returned unchanged.
 *
 * The model is asked for a sentence in `cash_flow_analysis.status` and
 * `forecast.outlook` and does not always oblige — a shipped report read
 * "Статус: critical" and "Перспектива: negative". `warning_level` and
 * `confidence` are vocabularies by design and were merely `capitalize`d, which
 * turns "critical" into "Critical", not into Russian.
 *
 * Mirrors humanize() in app/services/ai_text.py; a test pins the token sets
 * together so the PDF and the page cannot drift apart.
 */
export function humanizeEnum(
  value: string | null | undefined,
  t: (key: string, opts?: Record<string, unknown>) => string,
  /**
   * "level" for a risk level. Russian agrees the adjective with the noun above
   * it: "Уверенность" takes ВЫСОКАЯ, "Уровень риска" takes ВЫСОКИЙ. One table
   * cannot serve both without one of them reading wrong.
   */
  kind?: "level"
): string {
  if (!value) return "";
  const key = value.trim().toLowerCase().replace(/[_-]/g, " ");
  if (kind === "level") {
    const levelKey = `report.enum_level.${key}`;
    const levelLabel = t(levelKey);
    if (levelLabel !== levelKey) return levelLabel;
  }
  const lookup = `report.enum.${key}`;
  const label = t(lookup);
  // i18next echoes the key back when it is missing, which is how prose is
  // told apart from a token without keeping a second copy of the list here.
  if (label !== lookup) return label;

  const words = key.split(" ");
  if (words.length === 2 && words.includes("critical") && words.includes("deficit")) {
    return t("report.enum.critical");
  }
  return value.trim();
}


/**
 * Reader-facing name for a transaction category.
 *
 * Categories used to render as their raw key, so an Uzbek report said
 * "payroll" — and any category the taxonomy did not know stayed in whatever
 * language the user typed, which is how "личные расходы" appeared untranslated
 * in the English and Uzbek reports.
 *
 * A key with no label is returned as-is: it came from the user's own file, and
 * inventing a translation is worse than showing what they wrote. Mirrors
 * category_label() in app/utils/category_mapper.py.
 */
export function categoryLabel(
  key: string | null | undefined,
  t: (k: string) => string
): string {
  if (!key) return "";
  const normalised = key.trim().toLowerCase().replace(/[\s_-]+/g, " ");
  // Resolve the name to a canonical key first. Not every caller passes a
  // normalised value — the anomalies table carries whatever the model wrote,
  // so it arrives as "личные расходы" rather than "personal".
  const aliasKey = `report.category_alias.${normalised}`;
  const alias = t(aliasKey);
  const canonical = alias === aliasKey ? normalised : alias;

  const lookup = `report.category.${canonical}`;
  const label = t(lookup);
  return label === lookup ? key : label;
}


/**
 * Merge category rows that differ only in case or surrounding whitespace.
 *
 * The engine now groups on a case-folded key, so newly generated reports
 * arrive already merged. This is for the ones ALREADY STORED: a saved report
 * keeps the split it was computed with, and re-rendering it must not show
 * "Marketing", "Marketing", "Marketing" as three wedges. The PDF has done this
 * at render time for the same reason.
 *
 * The first spelling encountered wins, matching the backend, so the two
 * surfaces name a category identically — which also keeps its colour stable,
 * since the palette is assigned by name.
 */
export function mergeCategoriesCI<T extends { category: string; total: number; percentage?: number; transaction_count?: number }>(
  rows: T[]
): T[] {
  const out = new Map<string, T>();
  for (const row of rows) {
    const key = row.category.trim().replace(/\s+/g, " ").toLowerCase();
    if (!key) continue;
    const seen = out.get(key);
    if (seen) {
      seen.total += row.total;
      if (typeof seen.percentage === "number" && typeof row.percentage === "number") {
        seen.percentage = Math.round((seen.percentage + row.percentage) * 100) / 100;
      }
      if (typeof seen.transaction_count === "number" && typeof row.transaction_count === "number") {
        seen.transaction_count += row.transaction_count;
      }
    } else {
      out.set(key, { ...row, category: row.category.trim().replace(/\s+/g, " ") });
    }
  }
  return [...out.values()].sort((a, b) => b.total - a.total);
}
