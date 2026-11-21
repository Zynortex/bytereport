import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { BarChart2, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { useAuthStore } from "@/store/authStore";
import { supportHandle, supportUrl } from "@/lib/support";
import { PLANS, formatPrice, type Plan } from "@/lib/pricing";
import { cn } from "@/lib/utils";

/**
 * Plans as they are actually sold today: three free reports at sign-up, and
 * two packages paid by card transfer and switched on by hand. There is no
 * online payment yet, so no button here pretends to take one — the paid plans
 * lead to the support contact, labelled as early access.
 *
 * Every number comes from pricing.json, the file the backend enforces.
 */
export default function Pricing() {
  const { t, i18n } = useTranslation();
  const { user } = useAuthStore();
  const lang = i18n.language || "ru";

  const reportsLine = (p: Plan) =>
    p.period === "once"
      ? t("pricing.reports_signup", { count: p.reports })
      : p.period === "month"
        ? t("pricing.reports_month", { count: p.reports })
        : t("pricing.reports_pack", { count: p.reports });

  return (
    <div className="min-h-screen bg-transparent font-sans">
      {/* Navbar */}
      <header className="sticky top-0 z-50 bg-header/90 backdrop-blur border-b border-brand-border">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
          <Link to="/" className="flex items-center gap-2 min-h-11 shrink-0">
            <div className="w-7 h-7 rounded border border-accent/70 flex items-center justify-center">
              <BarChart2 size={14} className="text-accent" />
            </div>
            <span className="font-bold text-brand-dark text-lg tracking-tight">ByteReport</span>
          </Link>
          <div className="flex items-center gap-2 sm:gap-3">
            <LanguageSwitcher variant="dark" />
            {user ? (
              <Button size="sm" asChild>
                <Link to="/dashboard">{t("pricing.to_app")}</Link>
              </Button>
            ) : (
              <>
                <Button variant="ghost" size="sm" asChild className="hidden sm:inline-flex">
                  <Link to="/auth">{t("pricing.login")}</Link>
                </Button>
                <Button size="sm" asChild>
                  <Link to="/auth?tab=register">{t("pricing.start_free")}</Link>
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="pt-16 sm:pt-20 pb-10 px-4 sm:px-6">
        <div className="max-w-3xl mx-auto">
          <p className="label-caps text-xs text-brand-blue mb-3">{t("pricing.eyebrow")}</p>
          <h1 className="text-display text-3xl sm:text-4xl font-extrabold text-brand-dark mb-4 text-balance">
            {t("pricing.title")}
          </h1>
          <p className="text-brand-muted text-base sm:text-lg max-w-2xl leading-relaxed">
            {t("pricing.subtitle", { count: PLANS.find((p) => p.id === "free")?.reports ?? 0 })}
          </p>
        </div>
      </section>

      {/* Plans */}
      <section className="pb-12 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto grid md:grid-cols-3 gap-4 sm:gap-5 items-stretch">
          {PLANS.map((p) => {
            const paid = p.price > 0;
            return (
              <div
                key={p.id}
                className={cn(
                  "rounded-xs border p-6 sm:p-7 flex flex-col",
                  paid ? "bg-surface-hover border-line-strong" : "bg-surface border-brand-border"
                )}
              >
                <p className="label-caps text-xs text-brand-muted mb-3">{t(`pricing.plan.${p.id}.name`)}</p>

                <div className="flex items-baseline gap-1.5 mb-1">
                  <span className="text-4xl font-extrabold text-brand-dark mono-num">
                    {formatPrice(p.price, lang)}
                  </span>
                  <span className="text-base font-semibold text-brand-dark">{t("pricing.currency")}</span>
                </div>
                <p className="text-sm text-brand-muted mb-5">{t(`pricing.plan.${p.id}.price_note`)}</p>

                <p className="text-sm font-semibold text-brand-dark mb-1">{reportsLine(p)}</p>
                <p className="text-sm text-brand-muted leading-relaxed flex-1 mb-6">
                  {t(`pricing.plan.${p.id}.for`)}
                </p>

                {!paid ? (
                  <Button variant="outline" className="w-full" asChild>
                    <Link to={user ? "/upload" : "/auth?tab=register"}>{t("pricing.start_free")}</Link>
                  </Button>
                ) : supportUrl ? (
                  <>
                    <Button className="w-full" asChild>
                      <a href={supportUrl} target="_blank" rel="noopener noreferrer">
                        {t("pricing.early_access")}
                      </a>
                    </Button>
                    <p className="text-xs text-brand-muted mt-2.5 leading-snug">{t("pricing.early_access_note")}</p>
                  </>
                ) : (
                  <>
                    {/* No contact configured yet: say how it works, link nowhere. */}
                    <Button className="w-full" disabled>
                      {t("pricing.early_access")}
                    </Button>
                    <p className="text-xs text-brand-muted mt-2.5 leading-snug">{t("pricing.early_access_pending")}</p>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Included everywhere */}
      <section className="pb-20 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto border-t border-brand-border pt-8 grid md:grid-cols-[1fr_2fr] gap-6">
          <div>
            <h2 className="text-display text-lg font-bold text-brand-dark mb-1">{t("pricing.included_title")}</h2>
            <p className="text-sm text-brand-muted">{t("pricing.notes_free")}</p>
          </div>
          <ul className="grid sm:grid-cols-2 gap-x-6 gap-y-3">
            {(["analysis", "score", "pdf", "notes"] as const).map((k) => (
              <li key={k} className="flex items-start gap-2.5 text-sm text-brand-dark">
                <CheckCircle size={15} className="text-brand-blue shrink-0 mt-0.5" />
                {t(`pricing.included.${k}`)}
              </li>
            ))}
          </ul>
        </div>

        {supportUrl && (
          <p className="max-w-5xl mx-auto text-sm text-brand-muted mt-10">
            {t("pricing.questions")}{" "}
            <a href={supportUrl} target="_blank" rel="noopener noreferrer" className="text-brand-blue hover:underline">
              {supportHandle}
            </a>
          </p>
        )}
      </section>
    </div>
  );
}
