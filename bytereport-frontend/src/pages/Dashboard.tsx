import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus, TrendingUp, FileText, Calendar, BarChart2, ArrowRight, Upload, MessageCircle, TrendingDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ScoreTrend, deltaToPrevious } from "@/components/dashboard/ScoreTrend";
import { HistoryRow } from "@/components/dashboard/HistoryRow";
import { useAuthStore } from "@/store/authStore";
import { FREE_REPORTS_ON_SIGNUP } from "@/lib/pricing";
import { useReportStore } from "@/store/reportStore";
import { scoreColor } from "@/lib/utils";
import type { ReportSummary } from "@/types";

export default function Dashboard() {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const { user } = useAuthStore();
  const { history, loadHistory, openReport, renameReport, deleteReport } = useReportStore();
  const [openingId, setOpeningId] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<ReportSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  // Set when a rename or delete changed only this device's copy.
  const [localOnly, setLocalOnly] = useState(false);
  const locale = i18n.language === "en" ? "en-US" : "ru-RU";

  useEffect(() => { loadHistory(user?.id); }, [loadHistory, user?.id]);

  const lastReport = history[0];
  const avgScore = history.length
    ? Math.round(history.reduce((s, r) => s + r.score, 0) / history.length)
    : null;

  const handleOpenReport = async (id: string) => {
    setOpeningId(id);
    await openReport(id);
    setOpeningId(null);
    navigate(`/report?id=${id}`);
  };

  const handleRename = async (id: string, name: string) => {
    const remote = await renameReport(id, name);
    setLocalOnly(!remote);
  };

  const confirmDelete = async () => {
    if (!toDelete) return;
    setDeleting(true);
    const remote = await deleteReport(toDelete.id);
    setDeleting(false);
    setToDelete(null);
    setLocalOnly(!remote);
  };

  const greeting = () => {
    const h = new Date().getHours();
    if (h < 12) return t("dashboard.greeting_morning");
    if (h < 18) return t("dashboard.greeting_day");
    return t("dashboard.greeting_evening");
  };

  const FEATURE_CARDS = [
    {
      icon: MessageCircle,
      iconColor: "text-brand-blue",
      iconBg: "bg-line/40",
      title: t("dashboard.feature_chat_title"),
      description: t("dashboard.feature_chat_desc"),
      badge: null as string | null,
      badgeClass: "",
      hint: t("dashboard.feature_chat_hint"),
      href: null as string | null,
    },
    {
      icon: TrendingDown,
      iconColor: "text-sev-medium",
      iconBg: "bg-sev-medium/15",
      title: t("dashboard.feature_cashflow_title"),
      description: t("dashboard.feature_cashflow_desc"),
      badge: t("dashboard.feature_cashflow_badge"),
      badgeClass: "bg-line/40 text-accent",
      hint: t("dashboard.feature_cashflow_hint"),
      href: null,
    },
    // Tax simulator card removed with its menu item (see Sidebar.tsx).
  ];

  // ── Empty state ───────────────────────────────────────────────────────────
  // One next step, said once. The demo is the second door for someone who
  // wants to see the result before handing over a statement.
  if (history.length === 0) {
    return (
      <div className="flex flex-col min-h-full">
        <div className="px-4 sm:px-6 md:px-8 pt-6 md:pt-8">
          <h1 className="text-xl font-bold text-brand-dark">
            {greeting()}, {user?.name ?? user?.email?.split("@")[0]}
          </h1>
        </div>

        <div className="flex-1 flex items-center justify-center p-4 sm:p-8">
          <div className="flex flex-col items-center text-center max-w-md">
            <div className="w-20 h-20 rounded-xs border border-brand-border flex items-center justify-center mb-7">
              <BarChart2 size={34} className="text-brand-blue" />
            </div>

            <h2 className="text-display text-2xl text-brand-dark mb-3 text-balance">
              {t("dashboard.empty_title")}
            </h2>
            <p className="text-brand-muted leading-relaxed mb-7">
              {t("dashboard.empty_text")}
            </p>

            <Button size="lg" className="w-full sm:w-auto px-8" asChild>
              <Link to="/upload">
                <Upload size={16} className="mr-2" />
                {t("dashboard.empty_cta")}
              </Link>
            </Button>
            <p className="text-xs text-brand-muted mt-3">
              {t("dashboard.empty_free", { count: FREE_REPORTS_ON_SIGNUP })}
            </p>

            <Link
              to="/demo"
              className="mt-6 inline-flex items-center gap-1.5 min-h-11 text-sm text-accent-fg hover:text-brand-dark transition-colors duration-200 ease-out"
            >
              {t("dashboard.empty_demo")}
              <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // ── Normal dashboard ───────────────────────────────────────────────────────
  return (
    <div className="p-4 sm:p-6 md:p-8">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6 md:mb-8">
        <div>
          <h1 className="font-heading text-2xl font-bold text-brand-dark">
            {greeting()}, {user?.name ?? user?.email?.split("@")[0]}
          </h1>
          <p className="text-brand-muted text-sm mt-0.5">
            {t(history.length === 1 ? "dashboard.reports_saved_one" : "dashboard.reports_saved", { count: history.length })}
          </p>
        </div>
        <Button asChild className="w-full sm:w-auto">
          <Link to="/upload">
            <Plus size={16} className="mr-2" />
            {t("dashboard.new_analysis")}
          </Link>
        </Button>
      </div>

      {/* Stats — three across from the first breakpoint; on a phone they share
          one row too, icons dropped, so the history is not pushed off-screen. */}
      <div className="grid grid-cols-3 gap-2 sm:gap-4 mb-6 md:mb-8">
        <Card>
          <CardContent className="p-3 sm:p-6 sm:pt-6">
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                <p className="text-[10px] sm:text-xs text-brand-muted uppercase tracking-wide font-semibold">{t("dashboard.reports_count")}</p>
                <p className="text-2xl sm:text-3xl font-extrabold text-brand-dark mt-1 mono-num">{history.length}</p>
              </div>
              <div className="hidden md:flex w-11 h-11 rounded-xl bg-line/40 items-center justify-center shrink-0">
                <FileText size={20} className="text-brand-blue" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-3 sm:p-6 sm:pt-6">
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                <p className="text-[10px] sm:text-xs text-brand-muted uppercase tracking-wide font-semibold">{t("dashboard.avg_score")}</p>
                <span className="block w-8 h-px bg-accent mt-1.5" aria-hidden="true" />
                <p
                  className="text-2xl sm:text-3xl text-score mt-2"
                  style={{ color: avgScore ? scoreColor(avgScore) : "var(--color-fg-muted)" }}
                >
                  {avgScore ?? "—"}
                </p>
              </div>
              <div className="hidden md:flex w-11 h-11 rounded-xl bg-line/40 items-center justify-center shrink-0">
                <TrendingUp size={20} className="text-fg-subtle" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-3 sm:p-6 sm:pt-6">
            <div className="flex items-center justify-between">
              <div className="min-w-0">
                <p className="text-[10px] sm:text-xs text-brand-muted uppercase tracking-wide font-semibold">{t("dashboard.last_analysis")}</p>
                <p className="text-sm font-semibold text-brand-dark mt-1">
                  {lastReport
                    ? new Date(lastReport.created_at).toLocaleDateString(locale, { day: "numeric", month: "long" })
                    : t("dashboard.no_data")}
                </p>
              </div>
              <div className="hidden md:flex w-11 h-11 rounded-xl bg-line/40 items-center justify-center shrink-0">
                <Calendar size={20} className="text-accent" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Score over time — from the second report on. */}
      {history.length >= 2 && (
        <div className="mb-6 md:mb-8">
          <ScoreTrend history={history} />
        </div>
      )}

      {/* Recent reports */}
      <Card className="mb-6 md:mb-8">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>{t("dashboard.history_title")}</CardTitle>
        </CardHeader>
        <CardContent>
          {localOnly && (
            <p className="text-xs text-sev-medium-fg border border-sev-medium/60 rounded-xs px-3 py-2 mb-3 anim-fade-in">
              {t("dashboard.local_only")}
            </p>
          )}
          <div>
            {history.map((r, i) => (
              <HistoryRow
                key={r.id}
                report={r}
                delta={deltaToPrevious(history, i)}
                opening={openingId === r.id}
                disabled={openingId !== null}
                last={i === history.length - 1}
                onOpen={() => handleOpenReport(r.id)}
                onRename={(name) => handleRename(r.id, name)}
                onDelete={() => setToDelete(r)}
              />
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Feature tools */}
      <div>
        <p className="text-xs font-semibold text-brand-muted uppercase tracking-wide mb-4">
          {t("dashboard.tools_title")}
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {FEATURE_CARDS.map((card) => {
            const Icon = card.icon;
            const inner = (
              <>
                {card.badge && (
                  <span className={`absolute top-4 right-4 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${card.badgeClass}`}>
                    {card.badge}
                  </span>
                )}
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center mb-3 ${card.iconBg}`}>
                  <Icon size={20} className={card.iconColor} />
                </div>
                <h3 className="text-sm font-bold text-brand-dark mb-1">{card.title}</h3>
                <p className="text-xs text-brand-muted leading-relaxed">{card.description}</p>
                {card.hint && (
                  <p className="text-[11px] text-brand-muted/60 mt-2 leading-tight">{card.hint}</p>
                )}
              </>
            );
            return card.href ? (
              <Link
                key={card.title}
                to={card.href}
                className="relative bg-transparent border border-brand-border rounded-xl p-5 sm:p-6 text-left transition-colors duration-200 ease-out hover:border-accent"
              >
                {inner}
              </Link>
            ) : (
              <div
                key={card.title}
                className="relative bg-transparent border border-brand-border rounded-xl p-5 sm:p-6 text-left"
              >
                {inner}
              </div>
            );
          })}
        </div>
      </div>

      <ConfirmDialog
        open={toDelete !== null}
        title={t("dashboard.delete_title")}
        text={t("dashboard.delete_text", { name: toDelete?.business_name ?? "" })}
        confirmLabel={t("dashboard.delete_confirm")}
        cancelLabel={t("dashboard.cancel")}
        busy={deleting}
        onConfirm={confirmDelete}
        onCancel={() => { if (!deleting) setToDelete(null); }}
      />

    </div>
  );
}
