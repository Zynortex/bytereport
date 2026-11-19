/**
 * Health Score breakdown → sentences.
 *
 * The checks and their numbers come from the engine
 * (financial_engine.health_score_breakdown); the sentences from
 * report-copy.json → score_breakdown, which the PDF reads too. The number
 * formatting below mirrors bytereport/app/services/report_copy.py
 * (breakdown_lines) and a test pins the two together, so both surfaces print
 * the same sentence for the same check.
 */
import type { TFunction } from "i18next";
import type { HealthBreakdownItem } from "@/types";

const MINUS = "\u2212";

const pct = (v: number) => Number(v).toFixed(1);
const signed = (v: number) => (v > 0 ? `+${Number(v).toFixed(1)}` : v < 0 ? `${MINUS}${Math.abs(v).toFixed(1)}` : "0.0");
const amount = (v: number) => Math.round(Number(v)).toLocaleString("en-US").replace(/,/g, "\u00a0");

export function formatPoints(points: number): string {
  return points > 0 ? `+${points}` : points < 0 ? `${MINUS}${Math.abs(points)}` : "0";
}

function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (m, k) => (k in values ? String(values[k]) : m));
}

export function breakdownLines(items: HealthBreakdownItem[], t: TFunction): Array<{ points: number; text: string }> {
  return items.map((item) => {
    const v: Record<string, string | number> = { ...item.values };
    if ("margin" in v) v.margin = pct(Number(v.margin));
    if ("change" in v) v.change = signed(Number(v.change));
    if ("pct" in v) v.pct = pct(Number(v.pct));
    if ("amount" in v) v.amount = amount(Number(v.amount));
    return { points: item.points, text: fill(t(`score_breakdown.${item.key}_${item.variant}`), v) };
  });
}

/** 100 + points, held to 0–100 — true when the hold changed the result. */
export function wasCapped(items: HealthBreakdownItem[]): boolean {
  const raw = 100 + items.reduce((s, i) => s + i.points, 0);
  return raw < 0 || raw > 100;
}
