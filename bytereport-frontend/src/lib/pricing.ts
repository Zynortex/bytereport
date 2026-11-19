/**
 * Plan numbers, imported from repo-root pricing.json — the same file the
 * backend reads for the signup bonus. The page and the code that enforces it
 * can no longer disagree ("1 отчёт в месяц" on the page, 3 a day in the code).
 * Names and descriptions are translated in the locale files; only numbers
 * live in the JSON.
 */
import pricing from "../../../pricing.json";

export type PlanId = "free" | "owner" | "accountant";

export interface Plan {
  id: PlanId;
  price: number;
  reports: number;
  /** once = at sign-up; none = no expiry; month = per month */
  period: "once" | "none" | "month";
}

export const PLANS = pricing.plans as Plan[];
export const PRICING_CURRENCY: string = pricing.currency;
export const FREE_REPORTS_ON_SIGNUP: number = pricing.free_reports_on_signup;

/** 150000 → "150 000" (ru/uz) or "150,000" (en). */
export function formatPrice(value: number, lang: string): string {
  return value.toLocaleString(lang.startsWith("en") ? "en-US" : "ru-RU");
}
