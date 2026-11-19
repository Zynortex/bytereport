/**
 * Demo Report page — publicly accessible at /demo, no auth required.
 *
 * The dataset below is a fictional but internally consistent scenario: every
 * total is the sum of its parts, monthly figures reconcile to the quarter, and
 * the 13 weekly nets add up to the quarter's profit. It is labelled as an
 * example everywhere it appears — nothing here claims to be a real customer.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { ArrowLeft, BarChart2, Download, Loader2, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { HealthScoreCard } from "@/components/report/HealthScoreCard";
import { MonthlyChart } from "@/components/report/MonthlyChart";
import { CategoryPieChart } from "@/components/report/CategoryPieChart";
import { GrowthLineChart } from "@/components/report/GrowthLineChart";
import { InsightsGrid } from "@/components/report/InsightsGrid";
import { RisksTable } from "@/components/report/RisksTable";
import { AnomaliesTable } from "@/components/report/AnomaliesTable";
import { PriorityActions } from "@/components/report/PriorityActions";
import { PulseLine } from "@/components/ui/PulseLine";
import { AIChatPanel } from "@/components/chat/AIChatPanel";
import { ReportLanguageBadge } from "@/components/report/ReportLanguageBadge";
import { api } from "@/api/endpoints";
import { parseApiError } from "@/api/client";
import { warmOnIntent } from "@/api/serverWake";
import { formatCurrency, humanizeEnum } from "@/lib/utils";
import { DEMO_VARIANTS, getDemo } from "@/data/demoReport";

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card>
      <CardContent className="pt-6 pb-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-brand-muted mb-1.5">{label}</p>
        <p className="text-2xl font-extrabold text-brand-dark mono-num">{value}</p>
        {sub && <p className="text-xs text-brand-muted mt-1.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

// Development only: the same seed data, reachable from a browser-driven check.
if (import.meta.env.DEV) {
  const ru = DEMO_VARIANTS.ru;
  (window as unknown as { __demoData?: unknown }).__demoData = {
    REPORT: ru.report, METRICS: ru.metrics, DEMO_INFO: ru.info, VARIANTS: DEMO_VARIANTS,
  };
}

export default function Demo() {
  const { t, i18n } = useTranslation();
  // The demo in the interface language (Russian or English; numbers equal).
  const demo = getDemo(i18n.language);
  const { report: REPORT, metrics: METRICS, info: DEMO_INFO } = demo;
  const cur = DEMO_INFO.currency;
  const [chatOpen, setChatOpen] = useState(false);
  // The chat runs a real model on our budget, so an anonymous visitor is
  // pointed at sign-up instead of at a 401. The PDF button stays open: it
  // renders locally and costs nothing upstream.
  const { user } = useAuthStore();
  const [pdfBusy, setPdfBusy] = useState(false);

  // Same endpoint and generator the real report uses — the demo is not a
  // special case, it just passes its own fixture through.
  const handleDownloadPDF = async () => {
    setPdfBusy(true);
    try {
      const blob = await api.downloadPDF(REPORT, DEMO_INFO, METRICS);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "bytereport_demo.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      // Show what actually went wrong; "PDF error" told the user nothing they
      // could act on.
      alert(`${t("report.pdf_error")} ${parseApiError(err)}`);
    } finally {
      setPdfBusy(false);
    }
  };
  const wcf = REPORT.weekly_cash_flow ?? [];
  const negativeWeeks = wcf.filter((w) => w.net < 0);
  const peak = wcf.reduce((a, b) => (b.net > a.net ? b : a), wcf[0]);

  return (
    <div className="min-h-screen bg-ground">

      {/* Top bar */}
      <div className="bg-header px-4 md:px-6 py-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2">
          <Link to="/" className="flex items-center gap-2 min-h-11 hover:opacity-80 transition-opacity" aria-label={t("demo.aria_home")}>
            <span className="w-6 h-6 rounded border border-accent/70 flex items-center justify-center">
              <BarChart2 size={13} className="text-accent" />
            </span>
            <span className="text-brand-dark font-bold text-sm">ByteReport</span>
          </Link>
          <span className="text-brand-muted text-xs ml-2">{t("demo.badge")}</span>
        </div>
        <div className="grid grid-cols-2 gap-2 md:flex md:items-center md:gap-3">
          <span className="text-brand-muted text-xs hidden lg:block">{demo.headerLabel}</span>
          <Button size="sm" variant="outline" onClick={handleDownloadPDF} disabled={pdfBusy} className="max-md:h-auto max-md:min-h-11 max-md:py-2 max-md:whitespace-normal max-md:text-center">
            {pdfBusy ? <Loader2 size={14} className="mr-2 animate-spin" /> : <Download size={14} className="mr-2" />}
            {t("report.download_pdf")}
          </Button>
          {user ? (
            <Button size="sm" variant="outline" onClick={() => setChatOpen(true)} className="max-md:h-auto max-md:min-h-11 max-md:py-2 max-md:whitespace-normal max-md:text-center">
              <MessageSquare size={14} className="mr-2" />
              {t("report.ask_ai_cfo")}
            </Button>
          ) : (
            <Button size="sm" variant="outline" asChild title={t("report.demo_chat_hint")} className="max-md:h-auto max-md:min-h-11 max-md:py-2 max-md:whitespace-normal max-md:text-center">
              <Link to="/auth?tab=register" {...warmOnIntent}>
                <MessageSquare size={14} className="mr-2" />
                {t("report.demo_chat_signin")}
              </Link>
            </Button>
          )}
          <Button size="sm" asChild className="col-span-2 order-first md:order-none">
            <Link to="/auth?tab=register" {...warmOnIntent}>{t("demo.cta_try")}</Link>
          </Button>
        </div>
      </div>

      {/* Demo banner */}
      <div className="bg-sev-medium/15 border-b border-sev-medium/40 px-4 md:px-6 py-2 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-sev-medium">
          <span className="font-semibold">{t("demo.banner_bold")}</span> {t("demo.banner_text")}
        </p>
        <Link to="/" className="text-xs text-sev-medium hover:underline flex items-center gap-1 max-sm:min-h-11">
          <ArrowLeft size={11} /> {t("demo.back_home")}
        </Link>
      </div>

      {/* Report content */}
      <div className="p-4 sm:p-6 md:p-8 space-y-6 md:space-y-8 max-w-6xl mx-auto">

        {/* Header */}
        <div>
          <h1 className="text-display text-2xl text-brand-dark">{DEMO_INFO.name}</h1>
          <p className="text-brand-muted text-sm mt-1">
            {demo.businessLine} · {demo.periodLabel}
          </p>
          <p className="text-xs text-brand-muted/80 mt-1.5">
            {t("report.data_source", { count: METRICS.transaction_count, period: demo.periodLabel })}
          </p>
          <div className="mt-2 empty:hidden">
            <ReportLanguageBadge language={REPORT.language} />
          </div>
        </div>

        {/* Health score + summary */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <HealthScoreCard score={REPORT.financial_health_score} />
          <div className="lg:col-span-2">
            <Card className="h-full">
              <CardContent className="pt-6">
                <p className="text-xs font-semibold uppercase tracking-widest text-brand-muted mb-3">
                  {t("report.executive_summary")}
                </p>
                <p className="text-sm text-brand-dark leading-relaxed">{REPORT.executive_summary}</p>
                <Separator className="my-4" />
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <p className="text-brand-muted text-xs mb-0.5">{t("report.cash_flow")}</p>
                    <p className="font-semibold text-brand-dark">{humanizeEnum(REPORT.cash_flow_analysis.status, t)}</p>
                  </div>
                  <div>
                    <p className="text-brand-muted text-xs mb-0.5">{t("report.forecast_label")}</p>
                    <p className="font-semibold text-brand-dark">{humanizeEnum(REPORT.forecast.outlook, t)}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* KPI */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label={t("demo.kpi_revenue")}  value={formatCurrency(METRICS.total_revenue, cur)}  sub={t("demo.per_month", { value: formatCurrency(METRICS.avg_monthly_revenue, cur) })} />
          <StatCard label={t("demo.kpi_expenses")} value={formatCurrency(METRICS.total_expenses, cur)} sub={t("demo.per_month", { value: formatCurrency(METRICS.avg_monthly_expenses, cur) })} />
          <StatCard label={t("demo.kpi_profit")}   value={formatCurrency(METRICS.profit, cur)}         sub={t("demo.margin", { value: METRICS.profit_margin })} />
          <StatCard label={t("demo.kpi_mom")}      value="+86.2%"                                     sub={t("demo.kpi_mom_sub")} />
        </div>

        {/* Кассовый разрыв / недельный поток */}
        <Card>
          <CardContent className="pt-6 pb-6">
            <div className="flex flex-wrap items-start justify-between gap-3 mb-1">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-brand-muted">
                  {t("report.weekly_cash_flow")}
                </p>
                <p className="text-sm text-brand-dark mt-1.5 leading-relaxed max-w-2xl">
                  {demo.weeklyNote}
                </p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-xs text-brand-muted">{t("report.peak_week")}</p>
                <p className="text-lg font-bold text-brand-dark mono-num">
                  {formatCurrency(peak.net, cur)}
                </p>
                <p className="text-xs text-brand-muted">{peak.week}</p>
              </div>
            </div>

            <PulseLine data={wcf} height={92} className="w-full mt-4" />

            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mt-3 text-xs text-brand-muted">
              <span className="inline-flex items-center gap-1.5">
                <span className="w-3 h-0.5 rounded-full bg-success" /> {t("demo.week_plus")}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-3 h-0.5 rounded-full bg-danger" /> {t("demo.week_minus")}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-accent" /> {t("report.peak_week")}
              </span>
              <span className="ml-auto">
                {t("demo.weeks_negative", { n: negativeWeeks.length, total: wcf.length })}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Charts */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <MonthlyChart data={METRICS.monthly_breakdown} currency={cur} />
          <CategoryPieChart data={METRICS.expense_by_category} currency={cur} />
        </div>

        <GrowthLineChart data={METRICS.mom_growth} outliers={METRICS.mom_outliers} />

        <InsightsGrid insights={REPORT.key_insights} />

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
          <RisksTable risks={REPORT.top_risks} />
          <AnomaliesTable anomalies={REPORT.anomalies} />
        </div>

        <PriorityActions actions={REPORT.priority_actions} />

        {/* CTA */}
        <Card className="border-brand-blue/20 bg-line/40/40">
          <CardContent className="pt-6 pb-6 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div>
              <p className="font-semibold text-brand-dark">{t("demo.cta_title")}</p>
              <p className="text-sm text-brand-muted mt-0.5">{t("demo.cta_text")}</p>
            </div>
            <Button size="lg" asChild className="shrink-0">
              <Link to="/auth?tab=register" {...warmOnIntent}>{t("demo.cta_start")}</Link>
            </Button>
          </CardContent>
        </Card>

      </div>

      <AIChatPanel
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        metrics={METRICS}
        report={REPORT}
        businessInfo={DEMO_INFO}
      />
    </div>
  );
}
