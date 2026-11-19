import { useEffect, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Download, Upload, TrendingUp, TrendingDown, Minus, AlertCircle, MessageSquare } from "lucide-react";
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
import { CashForecastCard } from "@/components/report/CashForecastCard";
import { ReportLanguageBadge } from "@/components/report/ReportLanguageBadge";
import { useReportStore } from "@/store/reportStore";
import { formatCurrency, humanizeEnum } from "@/lib/utils";
import { api } from "@/api/endpoints";
import { parseApiError } from "@/api/client";
import { AIChatPanel } from "@/components/chat/AIChatPanel";
import { PulseLine } from "@/components/ui/PulseLine";
import { BlockFrame, LayoutBar } from "@/components/report/LayoutControls";
import { keepItems, moveBlock, setVisible, toggleItem } from "@/lib/reportBlocks";

function StatCard({ label, value, sub, trend }: { label: string; value: string; sub?: string; trend?: number }) {
  return (
    <Card>
      <CardContent className="pt-5 pb-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-brand-muted mb-1.5">{label}</p>
        <p className="text-2xl font-extrabold text-brand-dark mono-num">{value}</p>
        {sub !== undefined && (
          <div className="flex items-center gap-1 mt-1">
            {trend !== undefined && trend !== 0 ? (
              trend > 0 ? <TrendingUp size={12} className="text-fg-subtle" /> : <TrendingDown size={12} className="text-sev-high" />
            ) : (
              <Minus size={12} className="text-brand-muted" />
            )}
            <span className="text-xs text-brand-muted">{sub}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function Report() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const reportId = searchParams.get("id");
  const { report, metrics, businessInfo, openReport, layout, setLayout, resetLayout, setMetrics } = useReportStore();
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(!report || !metrics);
  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    if (report && metrics) {
      setLoading(false);
      return;
    }
    if (!reportId) {
      navigate("/upload", { replace: true });
      return;
    }
    setLoading(true);
    openReport(reportId).then((ok) => {
      if (!ok) navigate("/upload", { replace: true });
      else setLoading(false);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportId]);

  // A skeleton of the report, not a spinner: the page that is coming has a
  // known shape, so showing that shape is more informative than a rotating
  // circle — and the switch to real content is a fade rather than a jump.
  if (loading) {
    return (
      <div className="p-8 space-y-8 anim-fade-in" aria-busy="true" aria-label={t("report.loading")}>
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <div className="skeleton h-7 w-64" />
            <div className="skeleton h-4 w-40" />
          </div>
          <div className="skeleton h-10 w-36" />
        </div>
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="skeleton h-[340px] lg:col-span-1" />
          <div className="skeleton h-[340px] lg:col-span-2" />
        </div>
        <div className="grid md:grid-cols-2 gap-6">
          <div className="skeleton h-[280px]" />
          <div className="skeleton h-[280px]" />
        </div>
        <div className="skeleton h-40" />
      </div>
    );
  }

  if (!report || !metrics) return null;

  const handleDownloadPDF = async () => {
    try {
      // The same layout the page is rendering from. This is the feature: the
      // file is the arrangement on screen, not a fixed order of its own.
      const blob = await api.downloadPDF(report, businessInfo, metrics, layout);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `bytereport_${businessInfo.name || "report"}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      // Show what actually went wrong; "PDF error" told the user nothing they
      // could act on.
      alert(`${t("report.pdf_error")} ${parseApiError(err)}`);
    }
  };

  const lastGrowth = metrics.mom_growth.at(-1);

  // Three-level category signal. Older saved reports carry only the legacy
  // boolean (or nothing at all), so fall back through it to "full".
  const categoryLevel =
    metrics.category_reliability ??
    (metrics.has_reliable_categories === false ? "none" : "full");
  const coveragePercent = Math.round((metrics.category_coverage ?? 1) * 100);



  // ── Layout ────────────────────────────────────────────────────────────────
  const keep = <T,>(id: string, items: T[]) => keepItems(layout, id, items);
  const itemTitles: Record<string, string[]> = {
    key_insights:         report.key_insights.map((i) => i.title),
    top_risks:            report.top_risks.map((r) => r.risk),
    anomalies:            report.anomalies.map((a) => `${a.category} — ${a.issue}`),
    growth_opportunities: report.growth_opportunities.map((g) => g.opportunity),
    priority_actions:     report.priority_actions.map((a) => a.action),
  };

  const sections: Record<string, () => React.ReactNode> = {
    health_score: () => <HealthScoreCard score={report.financial_health_score} breakdown={metrics.health_breakdown} />,
    executive_summary: () => (
      <Card className="h-full">

          <Card className="h-full">
            <CardContent className="pt-6">
              <p className="text-xs font-semibold uppercase tracking-widest text-brand-muted mb-3">
                {t("report.executive_summary")}
              </p>
              <p className="text-sm text-brand-dark leading-relaxed">{report.executive_summary}</p>
              {report.weekly_cash_flow && report.weekly_cash_flow.length >= 2 && (
                <div className="mt-5">
                  <div className="flex items-center justify-between mb-1.5">
                    <p className="text-xs font-semibold uppercase tracking-wide text-brand-muted">
                      {t("report.weekly_cash_flow")}
                    </p>
                    <span className="inline-flex items-center gap-1.5 text-[11px] text-brand-muted">
                      <span className="w-2 h-2 rounded-full bg-accent" />
                      {t("report.peak_week")}
                    </span>
                  </div>
                  <PulseLine data={report.weekly_cash_flow} height={72} className="w-full" />
                </div>
              )}
              <Separator className="my-4" />
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-brand-muted text-xs mb-0.5">{t("report.cash_flow")}</p>
                  <p className="font-semibold text-brand-dark">{humanizeEnum(report.cash_flow_analysis.status, t)}</p>
                </div>
                <div>
                  <p className="text-brand-muted text-xs mb-0.5">{t("report.forecast_label")}</p>
                  <p className="font-semibold text-brand-dark">{humanizeEnum(report.forecast.outlook, t)}</p>
                </div>
                <div>
                  <p className="text-brand-muted text-xs mb-0.5">{t("report.risk_level")}</p>
                  <p className="font-semibold text-brand-dark">{humanizeEnum(report.cash_flow_analysis.warning_level, t, "level")}</p>
                </div>
                <div>
                  <p className="text-brand-muted text-xs mb-0.5">{t("report.confidence")}</p>
                  <p className="font-semibold text-brand-dark">{humanizeEnum(report.forecast.confidence, t)}</p>
                </div>
              </div>
            </CardContent>
          </Card>
      </Card>
    ),
    kpi_strip: () => (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label={t("report.revenue")}
          value={formatCurrency(metrics.total_revenue, businessInfo.currency)}
          sub={t("report.avg_per_month", { value: formatCurrency(metrics.avg_monthly_revenue, businessInfo.currency) })}
        />
        <StatCard
          label={t("report.expenses")}
          value={formatCurrency(metrics.total_expenses, businessInfo.currency)}
          sub={t("report.avg_per_month", { value: formatCurrency(metrics.avg_monthly_expenses, businessInfo.currency) })}
        />
        <StatCard
          label={t("report.profit")}
          value={formatCurrency(metrics.profit, businessInfo.currency)}
          sub={t("report.margin", { value: metrics.profit_margin.toFixed(1) })}
          trend={metrics.profit}
        />
        <StatCard
          label={t("report.mom_growth")}
          value={lastGrowth?.revenue_growth_pct != null ? `${lastGrowth.revenue_growth_pct > 0 ? "+" : ""}${lastGrowth.revenue_growth_pct.toFixed(1)}%` : "—"}
          sub={t("report.last_month")}
          trend={lastGrowth?.revenue_growth_pct ?? 0}
        />
      </div>
    ),
    chart_monthly: () => <MonthlyChart data={metrics.monthly_breakdown} currency={businessInfo.currency} />,
    chart_categories: () => (
      <>

        {categoryLevel === "none" ? (
          <Card>
            <CardContent className="pt-6 pb-6">
              <p className="text-xs font-semibold uppercase tracking-wide text-brand-muted mb-2">
                {t("report.categories_title")}
              </p>
              <p className="text-sm text-brand-muted leading-relaxed">
                {t("report.no_categories_note")}
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="flex flex-col gap-2">
            <CategoryPieChart data={metrics.expense_by_category} currency={businessInfo.currency} />
            {categoryLevel === "partial" && (
              <p className="text-xs text-warning leading-relaxed px-1">
                {t("report.partial_categories_note", { percent: coveragePercent })}
              </p>
            )}
          </div>
        )}
      </>
    ),
    chart_growth: () => (
      <>
      {metrics.mom_growth.length > 0 && (
        <GrowthLineChart data={metrics.mom_growth} outliers={metrics.mom_outliers} />
      )}
      </>
    ),
    chart_forecast: () => (
      <CashForecastCard
        metrics={metrics}
        currency={businessInfo.currency}
        onForecast={(cashflow_forecast) => setMetrics({ ...metrics, cashflow_forecast })}
      />
    ),
    key_insights: () => <InsightsGrid insights={keep('key_insights', report.key_insights)} />,
    top_risks: () => <RisksTable risks={keep('top_risks', report.top_risks)} />,
    anomalies: () => <AnomaliesTable anomalies={keep('anomalies', report.anomalies)} />,
    expense_analysis: () => (
      <>
        {(report.expense_analysis.problem_categories.length > 0 || report.expense_analysis.efficient_categories.length > 0) && (
        <Card>
          <CardContent className="pt-6">
            <h3 className="text-sm font-semibold uppercase tracking-widest text-brand-muted mb-4">
              {t("report.expense_analysis")}
            </h3>
            <div className="grid md:grid-cols-2 gap-4">
              {report.expense_analysis.problem_categories.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-sev-high mb-2">{t("report.problem_categories")}</p>
                  <div className="space-y-1.5">
                    {report.expense_analysis.problem_categories.map((c) => (
                      <div key={String(c)} className="flex items-center gap-2">
                        <AlertCircle size={12} className="text-sev-high shrink-0" />
                        <span className="text-sm text-brand-dark">{String(c)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {report.expense_analysis.efficient_categories.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-fg-subtle mb-2">{t("report.efficient_categories")}</p>
                  <div className="space-y-1.5">
                    {report.expense_analysis.efficient_categories.map((c) => (
                      <div key={String(c)} className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-xs bg-success shrink-0" />
                        <span className="text-sm text-brand-dark">{String(c)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            {report.expense_analysis.notes && (
              <p className="text-xs text-brand-muted mt-4">{report.expense_analysis.notes}</p>
            )}
          </CardContent>
        </Card>
      )}
      </>
    ),
    growth_opportunities: () => (
      keep("growth_opportunities", report.growth_opportunities).length > 0 ? (
        <Card>
          <CardContent className="pt-6">
            <h3 className="text-sm font-semibold uppercase tracking-widest text-brand-muted mb-4">
              {t("report.growth_opportunities")}
            </h3>
            <div className="grid md:grid-cols-2 gap-3">
              {keep("growth_opportunities", report.growth_opportunities).map((g, i) => (
                <div key={i} className="rounded-xs border border-brand-border p-4">
                  <p className="text-sm font-semibold text-brand-dark mb-1">{g.opportunity}</p>
                  <p className="text-xs text-brand-muted mb-2">{g.potential_impact}</p>
                  <p className="text-xs text-brand-dark">{g.action}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null
    ),
    priority_actions: () => <PriorityActions actions={keep('priority_actions', report.priority_actions)} />,
    cash_flow_analysis: () => (
      <Card>
        <CardContent className="pt-6">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-brand-muted mb-3">
            {t("report.cash_flow_analysis")}
          </h3>
          <div className="flex gap-6 mb-3 text-sm">
            <div>
              <span className="text-brand-muted">{t("report.cash_flow")}: </span>
              <span className="font-semibold text-brand-dark">{humanizeEnum(report.cash_flow_analysis.status, t)}</span>
            </div>
            <div>
              <span className="text-brand-muted">{t("report.risk_level")}: </span>
              <span className="font-semibold text-brand-dark">{humanizeEnum(report.cash_flow_analysis.warning_level, t, "level")}</span>
            </div>
          </div>
          <p className="text-sm text-brand-dark leading-relaxed">{report.cash_flow_analysis.summary}</p>
        </CardContent>
      </Card>
    ),
    forecast: () => (
      <>
        <Card className="border-brand-blue/20 bg-line/40/30">
        <CardContent className="pt-6">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-brand-blue mb-3">
            {t("report.forecast_section")}
          </h3>
          <div className="flex gap-6 mb-3 text-sm">
            <div>
              <span className="text-brand-muted">{t("report.outlook")}: </span>
              <span className="font-semibold text-brand-dark">{humanizeEnum(report.forecast.outlook, t)}</span>
            </div>
            <div>
              <span className="text-brand-muted">{t("report.confidence_label")}: </span>
              <span className="font-semibold text-brand-dark">{humanizeEnum(report.forecast.confidence, t)}</span>
            </div>
          </div>
          <p className="text-sm text-brand-dark leading-relaxed">{report.forecast.summary}</p>
        </CardContent>
      </Card>
      </>
    ),
  };

  // Adjacent sections that share a row when the reader is not editing. In
  // edit mode everything is one column so a drag target is unambiguous.
  const PAIRS: Array<[Set<string>, string]> = [
    [new Set(["health_score", "executive_summary"]), "grid grid-cols-1 lg:grid-cols-3 gap-6 [&>*:nth-child(2)]:lg:col-span-2"],
    [new Set(["chart_monthly", "chart_categories", "chart_growth"]), "grid grid-cols-1 xl:grid-cols-2 gap-6"],
    [new Set(["top_risks", "anomalies"]), "grid grid-cols-1 xl:grid-cols-2 gap-8"],
  ];

  const renderSections = () => {
    const blocks = layout.blocks;
    const out: React.ReactNode[] = [];
    let i = 0;
    while (i < blocks.length) {
      const b = blocks[i];
      const render = sections[b.id];
      if (!render) { i += 1; continue; }

      const frame = (idx: number, blk: { id: string; visible: boolean }, node: React.ReactNode) => (
        <BlockFrame
          key={blk.id} id={blk.id} index={idx} count={blocks.length}
          visible={blk.visible} editing={editing}
          items={itemTitles[blk.id]} hiddenItems={layout.hidden_items[blk.id]}
          onToggle={(id, v) => setLayout(setVisible(layout, id, v))}
          onMove={(from, to) => setLayout(moveBlock(layout, from, to))}
          onToggleItem={itemTitles[blk.id] ? (id, n) => setLayout(toggleItem(layout, id, n)) : undefined}
        >
          {node}
        </BlockFrame>
      );

      // Pair with the next block when both are visible members of one group.
      const next = blocks[i + 1];
      const pair = !editing && next && b.visible && next.visible && sections[next.id]
        ? PAIRS.find(([ids]) => ids.has(b.id) && ids.has(next.id))
        : undefined;
      if (pair) {
        out.push(
          <div key={`${b.id}+${next.id}`} className={pair[1]}>
            {frame(i, b, render())}
            {frame(i + 1, next, sections[next.id]())}
          </div>
        );
        i += 2;
      } else {
        out.push(frame(i, b, render()));
        i += 1;
      }
    }
    return out;
  };

  return (
    <div className="p-4 sm:p-6 md:p-8 pb-28 md:pb-8 space-y-6 md:space-y-8">
      {/* Top bar */}
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <h1 className="text-display text-2xl text-brand-dark break-words">
            {businessInfo.name || t("report.default_title")}
          </h1>
          <p className="text-brand-muted text-sm mt-0.5">
            {businessInfo.type && `${businessInfo.type} · `}
            {businessInfo.period || `${metrics.period_start} — ${metrics.period_end}`}
            {` · ${t("report.transactions", { count: metrics.transaction_count })}`}
          </p>
          <div className="mt-2 empty:hidden">
            <ReportLanguageBadge language={report.language} />
          </div>
        </div>
        <div className="flex flex-wrap gap-2 sm:gap-3 items-start">
          <LayoutBar
            editing={editing} layout={layout}
            onEdit={setEditing} onReset={resetLayout} onApply={setLayout}
          />
          <Button variant="outline" size="sm" asChild>
            <Link to="/upload">
              <Upload size={14} className="mr-2" />
              {t("report.new_analysis")}
            </Link>
          </Button>
          <Button size="sm" onClick={handleDownloadPDF}>
            <Download size={14} className="mr-2" />
            {t("report.download_pdf")}
          </Button>
        </div>
      </div>

      {/* ── Sections, in the order the layout says ──────────────────────────
          Each section is a keyed render function. The page walks the layout
          and renders what it finds, so the order the accountant arranges is
          the order shown — and the same layout object is what the PDF is
          built from, so the file is that arrangement too. Nothing here has a
          fixed position any more. */}
      {renderSections()}

      {/* Bottom CTA */}
      <div className="flex justify-center pb-4">
        <Button size="lg" className="w-full sm:w-auto" onClick={handleDownloadPDF}>
          <Download size={16} className="mr-2" />
          {t("report.download_pdf_long")}
        </Button>
      </div>

      {/* Floating AI-CFO button. It floats over the report, so it gets a solid
          ground like every other overlay. hover:scale-105/active:scale-95 was
          the last scale-pop left in the app; the hover state is a border lift. */}
      <button
        onClick={() => setChatOpen(true)}
        aria-label={t("report.ask_ai_cfo")}
        // On a phone it is a 44px square: a labelled button covered two lines
        // of text at a time. The page keeps bottom padding so the last control
        // always scrolls clear of it.
        className="fixed bottom-4 right-4 md:bottom-6 md:right-6 z-30 flex items-center justify-center gap-2 h-11 w-11 md:w-auto md:h-auto bg-header border border-accent md:px-4 md:py-3 rounded-xs text-accent-fg hover:border-accent-fg hover:bg-accent/12 transition-colors duration-200 ease-out"
      >
        <MessageSquare size={18} />
        <span className="hidden md:inline text-xs label-caps">{t("report.ask_ai_cfo")}</span>
      </button>

      {/* Chat panel */}
      <AIChatPanel
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        metrics={metrics}
        report={report}
        businessInfo={businessInfo}
      />
    </div>
  );
}
