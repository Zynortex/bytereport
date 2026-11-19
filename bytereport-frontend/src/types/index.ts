// ── Backend model types ────────────────────────────────────────────────────

export interface Transaction {
  date: string;
  description: string;
  amount: number;
  type: "income" | "expense";
  category: string;
  raw_category?: string;
}

export interface ParseResult {
  transactions: Transaction[];
  total_rows: number;
  skipped_rows: number;
  warnings: string[];
}

export interface CategoryBreakdown {
  category: string;
  total: number;
  percentage: number;
  transaction_count: number;
}

export interface MonthMetrics {
  month: string;
  revenue: number;
  expenses: number;
  profit: number;
  profit_margin: number;
}

export interface MoMGrowth {
  month: string;
  revenue_growth_pct: number | null;
  expense_growth_pct: number | null;
  profit_growth_pct: number | null;
  /** Chart-safe copies: null when the base was near zero (growth_display.py). */
  revenue_growth_display?: number | null;
  expense_growth_display?: number | null;
  profit_growth_display?: number | null;
}

export interface MoMOutlier {
  month: string;
  metric: "revenue" | "expenses" | "profit";
  previous: number;
  current: number;
  pct: number;
}

export interface AnomalyFlag {
  category: string;
  month: string;
  type: "spike" | "drop" | "new_category" | "missing_category";
  severity: "low" | "medium" | "high";
  value: number;
  previous_value: number | null;
  change_pct: number | null;
  description: string;
}

export interface CashflowForecast {
  /**
   * True only when the user gave the account balance at the end of the
   * period. Without it the forecast is a net-flow trend: no date or amount of
   * a shortfall exists. Missing (older saved reports) means false.
   */
  balance_known?: boolean;
  closing_balance?: number | null;
  has_risk: boolean;
  risk_date: string | null;
  risk_amount: number | null;
  weekly_projection: Array<{
    week: number;
    /** null unless balance_known */
    projected_balance: number | null;
    projected_net?: number;
    projected_date?: string;
    projected_revenue?: number;
    projected_expenses?: number;
  }>;
  confidence: "LOW" | "MEDIUM" | "HIGH";
}

export interface WeeklyMetrics {
  week_key: string;
  month: string;
  week_number: number;
  revenue: number;
  expenses: number;
  profit: number;
}

/** One Health Score check, as the engine computed it (never the AI). */
export interface HealthBreakdownItem {
  key: string;
  variant: string;
  points: number;
  values: Record<string, number>;
}

export interface FinancialMetrics {
  /** Absent on reports saved before the engine kept it. */
  health_breakdown?: HealthBreakdownItem[];
  /** Present on every metrics object from /analyze; older saved reports may lack it. */
  weekly_breakdown?: WeeklyMetrics[];
  period_start: string;
  period_end: string;
  total_days: number;
  total_revenue: number;
  total_expenses: number;
  profit: number;
  profit_margin: number;
  avg_monthly_revenue: number;
  avg_monthly_expenses: number;
  avg_monthly_profit: number;
  revenue_by_category: CategoryBreakdown[];
  expense_by_category: CategoryBreakdown[];
  monthly_breakdown: MonthMetrics[];
  mom_growth: MoMGrowth[];
  mom_outliers?: MoMOutlier[];
  anomalies: AnomalyFlag[];
  transaction_count: number;
  income_count: number;
  expense_count: number;
  cashflow_forecast?: CashflowForecast;
  // Category-coverage signal, computed once on the backend
  // (category_coverage.py). Defaults describe categorised CSV/Excel, so older
  // saved reports without these fields keep their current behaviour.
  category_coverage?: number;
  category_reliability?: "full" | "partial" | "none";
  /** Legacy alias kept in sync by the backend: category_reliability !== "none". */
  has_reliable_categories?: boolean;
}

// ── AI Report types ────────────────────────────────────────────────────────

export interface WeeklyCashFlow {
  week: string;
  revenue: number;
  expenses: number;
  net: number;
}

export interface HealthScore {
  score: number;
  status: string;
  reasoning: string;
}

export interface KeyInsight {
  title: string;
  severity: "low" | "medium" | "high";
  explanation: string;
}

export interface TopRisk {
  risk: string;
  impact: string;
  recommendation: string;
}

export interface GrowthOpportunity {
  opportunity: string;
  potential_impact: string;
  action: string;
}

export interface ExpenseAnalysis {
  problem_categories: string[];
  efficient_categories: string[];
  notes: string;
}

export interface AnomalyReport {
  category: string;
  issue: string;
  severity: "low" | "medium" | "high";
  explanation: string;
}

export interface CashFlowAnalysis {
  status: string;
  summary: string;
  warning_level: string;
}

export interface Forecast {
  outlook: string;
  confidence: "low" | "medium" | "high";
  summary: string;
}

export interface PriorityAction {
  priority: number;
  action: string;
  expected_result: string;
}

export interface AIReport {
  /** Language the report text was generated in; absent on older reports. */
  language?: "ru" | "uz" | "en";
  executive_summary: string;
  financial_health_score: HealthScore;
  key_insights: KeyInsight[];
  top_risks: TopRisk[];
  growth_opportunities: GrowthOpportunity[];
  expense_analysis: ExpenseAnalysis;
  anomalies: AnomalyReport[];
  cash_flow_analysis: CashFlowAnalysis;
  forecast: Forecast;
  priority_actions: PriorityAction[];
  weekly_cash_flow?: WeeklyCashFlow[];
}

// ── Chat types ─────────────────────────────────────────────────────────────

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

// ── App types ──────────────────────────────────────────────────────────────

export interface BusinessInfo {
  name: string;
  type: string;
  period: string;
  currency: string;
  /** Account balance at the end of the statement period; optional. */
  closing_balance?: number | null;
}

export interface ReportSummary {
  id: string;
  business_name: string;
  business_type: string;
  period: string;
  score: number;
  status: string;
  created_at: string;
}

// ── Voice / free-text note ─────────────────────────────────────────────────

/** Fields the model may flag as uncertain. Closed set — see voice_note.py. */
export type DraftField = "date" | "amount" | "direction" | "description" | "category";

/**
 * One row as the model understood it. Distinct from `Transaction`: every field
 * here can be missing or wrong, which is precisely what the preview is for.
 */
export interface DraftTransaction {
  date: string | null;
  amount: number | null;
  direction: "income" | "expense";
  description: string;
  category: string | null;
  /**
   * Currency the amount is in. After the backend's FX pass this is the
   * business currency, and notes.amount cites the rate that got it there.
   */
  currency: string | null;
  /** Field names the model was unsure about. */
  uncertain: DraftField[];
  /** field name -> short reason, rendered inline next to that cell. */
  notes: Record<string, string>;
}

export interface ParseNoteResponse {
  transactions: DraftTransaction[];
  warnings: string[];
  source_text: string;
  /** Always false in this iteration — a single note cannot support analysis. */
  analysis_available: boolean;
  records_needed: number;
}

export interface TranscriptionResponse {
  text: string;
  detected_language: string | null;
  duration_seconds: number | null;
}

// ── Account ──────────────────────────────────────────────────────────────────

/** GET /account/credits. `balance` is null for an unlimited account. */
export interface Credits {
  balance: number | null;
  unlimited: boolean;
  signup_bonus: number;
  /** Ever granted reports by hand: "package used up", not "free reports used up". */
  paid?: boolean;
}
