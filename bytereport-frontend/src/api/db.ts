/**
 * Supabase database operations for ByteReport.
 *
 * saveReport  — writes report + transactions rows, returns the new report UUID
 * loadReports — fetches ReportSummary list for a user (newest first)
 */

import { supabase } from "@/lib/supabase";
import type {
  BusinessInfo,
  FinancialMetrics,
  AIReport,
  Transaction,
  ReportSummary,
} from "@/types";

// ── Save ─────────────────────────────────────────────────────────────────────

export async function saveReport(
  userId: string,
  info: BusinessInfo,
  metrics: FinancialMetrics,
  report: AIReport,
  transactions: Transaction[]
): Promise<string | null> {
  // 1. Insert report row
  const { data, error } = await supabase
    .from("reports")
    .insert({
      user_id:       userId,
      business_name: info.name  || null,
      business_type: info.type  || null,
      period:        info.period || null,
      currency:      info.currency,
      health_score:  report.financial_health_score.score,
      health_status: report.financial_health_score.status,
      metrics:       metrics  as unknown as Record<string, unknown>,
      ai_report:     report   as unknown as Record<string, unknown>,
    })
    .select("id")
    .single();

  if (error || !data) {
    console.error("[db] saveReport failed:", error?.message);
    return null;
  }

  const reportId = data.id as string;

  // 2. Insert transactions (cap at 1 000 rows to stay within request limits)
  if (transactions.length > 0) {
    const rows = transactions.slice(0, 1000).map((tx) => ({
      report_id:    reportId,
      user_id:      userId,
      date:         tx.date,
      description:  tx.description,
      amount:       tx.amount,
      type:         tx.type,
      category:     tx.category,
      raw_category: tx.raw_category ?? null,
    }));

    const { error: txErr } = await supabase.from("transactions").insert(rows);
    if (txErr) {
      // Non-critical: report is saved, transactions are bonus data
      console.warn("[db] transactions insert failed (non-critical):", txErr.message);
    }
  }

  return reportId;
}

// ── Load single report ────────────────────────────────────────────────────────

export interface FullReport {
  metrics:      FinancialMetrics;
  report:       AIReport;
  businessInfo: BusinessInfo;
}

export async function loadReport(reportId: string): Promise<FullReport | null> {
  const { data, error } = await supabase
    .from("reports")
    .select("metrics, ai_report, business_name, business_type, period, currency")
    .eq("id", reportId)
    .single();

  if (error || !data) {
    console.error("[db] loadReport failed:", error?.message);
    return null;
  }

  return {
    metrics:  data.metrics  as unknown as FinancialMetrics,
    report:   data.ai_report as unknown as AIReport,
    businessInfo: {
      name:     (data.business_name as string) ?? "",
      type:     (data.business_type as string) ?? "",
      period:   (data.period        as string) ?? "",
      currency: (data.currency      as string) ?? "UZS",
    },
  };
}

// ── Load list ─────────────────────────────────────────────────────────────────

export async function loadReports(userId: string): Promise<ReportSummary[]> {
  const { data, error } = await supabase
    .from("reports")
    .select("id, business_name, business_type, period, health_score, health_status, created_at")
    .eq("user_id", userId)
    .order("created_at", { ascending: false })
    .limit(20);

  if (error || !data) {
    console.error("[db] loadReports failed:", error?.message);
    return [];
  }

  return data.map((r) => ({
    id:            r.id            as string,
    business_name: r.business_name as string ?? "",
    business_type: r.business_type as string ?? "",
    period:        r.period        as string ?? "",
    score:         r.health_score  as number ?? 0,
    status:        r.health_status as string ?? "",
    created_at:    r.created_at    as string,
  }));
}

// ── Rename / delete ───────────────────────────────────────────────────────────
//
// Both ask PostgREST to return the rows it touched. Under RLS an UPDATE or
// DELETE the policies do not allow is not an error — it silently affects zero
// rows — so "no error" alone would report success for a change that never
// happened. Zero rows back is treated as a failure.

export async function renameReport(reportId: string, name: string): Promise<boolean> {
  const { data, error } = await supabase
    .from("reports")
    .update({ business_name: name })
    .eq("id", reportId)
    .select("id");
  if (error) console.error("[db] renameReport failed:", error.message);
  return !error && (data?.length ?? 0) > 0;
}

export async function deleteReport(reportId: string): Promise<boolean> {
  // Transactions first: if the foreign key has no ON DELETE CASCADE, the
  // report row cannot go while they reference it.
  const { error: txErr } = await supabase.from("transactions").delete().eq("report_id", reportId);
  if (txErr) console.warn("[db] deleteReport: transactions not deleted:", txErr.message);

  const { data, error } = await supabase
    .from("reports")
    .delete()
    .eq("id", reportId)
    .select("id");
  if (error) console.error("[db] deleteReport failed:", error.message);
  return !error && (data?.length ?? 0) > 0;
}
