import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { m } from "motion/react";
import { BarChart2, Upload, Cpu, FileText, ArrowRight, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PulseLine } from "@/components/ui/PulseLine";
import { WelcomeCard } from "@/components/ui/WelcomeCard";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { ScoreCounter } from "@/components/ui/ScoreCounter";
import { HeroBackdrop } from "@/components/landing/HeroBackdrop";
import { HeroReport } from "@/components/landing/HeroReport";
import { Reveal, RevealItem } from "@/components/landing/Reveal";
import { SpotlightCard } from "@/components/landing/SpotlightCard";
import { useAuthStore } from "@/store/authStore";
import { warmUp } from "@/api/serverWake";
import { FREE_REPORTS_ON_SIGNUP } from "@/lib/pricing";
import { getDemo } from "@/data/demoReport";
import { DUR, EASE, MS } from "@/lib/motionTokens";
import { cn, formatCurrency, scoreColor } from "@/lib/utils";

/**
 * The example card in "What's included": the score counts up while the
 * weekly net-flow trace draws beneath it, on one clock. Same demo data as
 * the hero and the /demo page — one scenario, not three sets of numbers.
 */
function ExampleReading() {
  const { t, i18n } = useTranslation();
  const demo = getDemo(i18n.language);
  const score = demo.report.financial_health_score.score;
  const weeks = demo.report.weekly_cash_flow ?? [];
  const money = (n: number) => formatCurrency(n, demo.info.currency);
  const ref = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setActive(true);
          io.disconnect();
        }
      },
      { threshold: 0.4 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div ref={ref} className="rounded-xs border border-brand-border p-6 sm:p-8">
      <div className="flex items-baseline justify-between mb-1">
        <p className="text-xs font-semibold uppercase tracking-widest text-brand-muted">{t("landing.ex_eyebrow")}</p>
        <span className="text-xs text-brand-muted">{t("landing.ex_period")}</span>
      </div>
      <span className="block w-10 h-px bg-accent mb-6" aria-hidden="true" />

      <div className="flex items-center gap-6 mb-7">
        <ScoreCounter
          value={score}
          active={active}
          duration={MS.draw}
          className="text-6xl text-score leading-none"
          style={{ color: scoreColor(score) }}
        />
        <div>
          <div className="text-sm font-semibold text-brand-dark">{t("landing.ex_status")}</div>
          <div className="text-xs text-brand-muted">{t("report.health_score_title")}</div>
        </div>
      </div>

      <PulseLine data={weeks} height={72} active={active} duration={MS.draw} className="w-full mb-1" />
      <p className="text-[11px] text-brand-muted mb-5">{t("landing.ex_pulse")}</p>

      <div className="space-y-2 text-sm">
        {[
          { label: t("landing.ex_revenue"),  value: money(demo.metrics.total_revenue) },
          { label: t("landing.ex_expenses"), value: money(demo.metrics.total_expenses) },
          { label: t("landing.ex_profit"),   value: money(demo.metrics.profit) },
        ].map((r) => (
          <div key={r.label} className="flex justify-between py-2 border-b border-brand-border last:border-0">
            <span className="text-brand-muted">{r.label}</span>
            <span className="font-semibold mono-num text-brand-dark">{r.value}</span>
          </div>
        ))}
      </div>

      <p className="text-[11px] text-brand-muted/80 mt-4 pt-3 border-t border-brand-border">
        {t("landing.ex_note")}
      </p>
    </div>
  );
}

/** True once the page has scrolled past `px` — the header firms up. */
function useScrolled(px = 8): boolean {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > px);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, [px]);
  return scrolled;
}

// Keys, not strings: resolved with t() inside the component so a language
// change re-renders them.
const FEATURES = [
  { icon: Upload,   key: "f1" },
  { icon: Cpu,      key: "f2" },
  { icon: FileText, key: "f3" },
];

const STEPS = ["s1", "s2", "s3"];

const CHECKS = ["c1", "c2", "c3", "c4", "c5", "c6"];

const EYEBROW = "label-caps text-xs text-accent-fg mb-3";

export default function Landing() {
  const { t } = useTranslation();
  const { user, isReady } = useAuthStore();
  const ctaPath = user ? "/dashboard" : "/auth?tab=register";
  const scrolled = useScrolled();

  // Wake the free backend while the visitor reads, so the first upload does
  // not wait for it. After first paint: it must not compete with the page.
  useEffect(() => {
    const id = window.setTimeout(warmUp, 1500);
    return () => window.clearTimeout(id);
  }, []);

  return (
    <div className="min-h-screen bg-transparent font-sans">
      {/* Header: transparent over the hero, then the header ground and a
          hairline fade in once the page scrolls. No blur — no glass. */}
      <header
        className={cn(
          "sticky top-0 z-50 border-b transition-[background-color,border-color] duration-[var(--dur-hover)] ease-out",
          scrolled ? "bg-header border-brand-border" : "bg-transparent border-transparent"
        )}
      >
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-2">
          <Link to="/" className="flex items-center gap-2 min-h-11 hover:opacity-80 transition-opacity" aria-label="ByteReport">
            <div className="w-7 h-7 rounded border border-accent/70 flex items-center justify-center">
              <BarChart2 size={14} className="text-accent" />
            </div>
            <span className="font-bold text-brand-dark text-lg tracking-tight">ByteReport</span>
          </Link>
          <nav className="hidden md:flex items-center gap-6 text-sm text-brand-muted">
            <a href="#features" className="hover:text-brand-dark transition-colors">{t("landing.nav_features")}</a>
            <a href="#how"      className="hover:text-brand-dark transition-colors">{t("landing.nav_how")}</a>
          </nav>
          <div className="flex items-center gap-1.5 sm:gap-3">
            {/* Always reachable, not only through the first-visit card:
                a returning visitor has dismissed that card for good. */}
            <LanguageSwitcher variant="dark" />
            {isReady && (
              user ? (
                <Button size="sm" asChild>
                  <Link to="/dashboard">{t("landing.to_dashboard")}</Link>
                </Button>
              ) : (
                <>
                  {/* On a phone the header holds one action; sign-in is the
                      second line of the hero CTA block and in the auth page. */}
                  <Button variant="ghost" size="sm" asChild className="hidden sm:inline-flex">
                    <Link to="/auth">{t("landing.login")}</Link>
                  </Button>
                  <Button size="sm" asChild>
                    <Link to={ctaPath}>{t("landing.start_free")}</Link>
                  </Button>
                </>
              )
            )}
          </div>
        </div>
      </header>

      {/* Hero: the copy paints at once (it is the LCP element — fading it in
          would delay it); the live mini-report beside it is what moves. */}
      <section className="relative overflow-hidden bg-header -mt-16 pt-16">
        <HeroBackdrop />
        <div className="relative max-w-6xl mx-auto px-4 sm:px-6 py-16 md:py-24 grid gap-12 lg:grid-cols-[1.05fr_1fr] lg:items-center">
          <div>
            <div className="inline-flex items-center gap-2 border border-accent/40 rounded-full px-3.5 py-1.5 text-xs text-fg-subtle mb-7">
              <span className="w-1.5 h-1.5 rounded-full bg-accent-fg" aria-hidden="true" />
              {t("landing.badge")}
            </div>
            {/* The accent phrase starts its own line on purpose. Flowing inline
                (or balanced), the web font's arrival re-wrapped the heading and
                moved the phrase — the only layout shift on the page. */}
            <h1 className="text-display text-[2.6rem] sm:text-6xl lg:text-[4.25rem] leading-[1.02] tracking-[-0.035em] text-brand-dark mb-6">
              {t("landing.hero_title_1")}
              <br />
              <span className="text-accent-fg">{t("landing.hero_title_2")}</span>
            </h1>
            <p className="text-base sm:text-lg text-fg-subtle max-w-[34rem] mb-9 leading-relaxed">
              {t("landing.hero_sub")}
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <Button size="lg" asChild className="text-sm">
                <Link to={ctaPath}>
                  {t("landing.cta_try")} <ArrowRight size={17} className="ml-1" />
                </Link>
              </Button>
              <Button size="lg" variant="outline" asChild className="text-sm">
                <Link to="/demo">{t("landing.cta_demo")}</Link>
              </Button>
            </div>
          </div>
          <div className="flex justify-center lg:justify-end">
            <HeroReport />
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-20 md:py-24">
        <Reveal className="max-w-6xl mx-auto px-4 sm:px-6">
          <RevealItem>
            <p className={cn(EYEBROW, "text-center")}>{t("landing.features_eyebrow")}</p>
            <h2 className="text-display text-3xl text-brand-dark text-center mb-12 text-balance">
              {t("landing.features_title")}
            </h2>
          </RevealItem>
          <div className="grid md:grid-cols-3 gap-5">
            {FEATURES.map(({ icon: Icon, key }) => (
              <RevealItem key={key}>
                <SpotlightCard className="h-full p-7">
                  <div className="w-10 h-10 rounded-xs border border-brand-border flex items-center justify-center mb-5">
                    <Icon size={20} strokeWidth={1.5} className="text-accent-fg" />
                  </div>
                  <h3 className="font-semibold text-brand-dark mb-2">{t(`landing.${key}_title`)}</h3>
                  <p className="text-sm text-brand-muted leading-relaxed">{t(`landing.${key}_desc`)}</p>
                </SpotlightCard>
              </RevealItem>
            ))}
          </div>
        </Reveal>
      </section>

      {/* What's included */}
      <section className="py-20 bg-ground">
        <Reveal className="max-w-6xl mx-auto px-4 sm:px-6 grid md:grid-cols-2 gap-12 items-center">
          <div>
            <RevealItem>
              <p className={EYEBROW}>{t("landing.checks_eyebrow")}</p>
              <h2 className="text-display text-3xl text-brand-dark mb-6 text-balance">{t("landing.checks_title")}</h2>
            </RevealItem>
            <div className="grid grid-cols-2 gap-y-3 gap-x-4">
              {CHECKS.map((c) => (
                <RevealItem key={c} className="flex items-center gap-2 text-sm text-brand-dark">
                  <CheckCircle size={15} strokeWidth={1.5} className="text-accent-fg shrink-0" />
                  {t(`landing.${c}`)}
                </RevealItem>
              ))}
            </div>
            <RevealItem>
              <Button size="lg" className="mt-8" asChild>
                <Link to={ctaPath}>{t("landing.start_analysis")}</Link>
              </Button>
            </RevealItem>
          </div>
          <RevealItem>
            <ExampleReading />
          </RevealItem>
        </Reveal>
      </section>

      {/* How it works: three steps joined by a line that draws as they
          arrive. Horizontal on wide screens, vertical on a phone. */}
      <section id="how" className="py-20 md:py-24">
        <Reveal className="max-w-6xl mx-auto px-4 sm:px-6" amount={0.3}>
          <RevealItem>
            <p className={cn(EYEBROW, "text-center")}>{t("landing.how_eyebrow")}</p>
            <h2 className="text-display text-3xl text-brand-dark text-center mb-14 text-balance">{t("landing.how_title")}</h2>
          </RevealItem>
          <div className="relative grid md:grid-cols-3 gap-10 md:gap-8">
            <m.span
              aria-hidden="true"
              className="hidden md:block absolute top-5 left-5 right-[calc(33.333%-1.25rem)] h-px bg-accent/70 origin-left"
              initial={{ scaleX: 0 }}
              whileInView={{ scaleX: 1 }}
              viewport={{ once: true, amount: 0.6 }}
              transition={{ duration: DUR.draw, ease: EASE, delay: DUR.reveal * 0.5 }}
            />
            <m.span
              aria-hidden="true"
              className="md:hidden absolute top-5 bottom-5 left-5 w-px bg-accent/70 origin-top"
              initial={{ scaleY: 0 }}
              whileInView={{ scaleY: 1 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: DUR.draw, ease: EASE, delay: DUR.reveal * 0.5 }}
            />
            {STEPS.map((s, i) => (
              <RevealItem key={s} className="relative pl-16 md:pl-0">
                <div className="absolute left-0 top-0 md:static w-10 h-10 rounded-xs border border-accent bg-ground flex items-center justify-center md:mb-5">
                  <span className="font-mono text-sm text-accent-fg tabular">{`0${i + 1}`}</span>
                </div>
                <h3 className="font-semibold text-brand-dark mb-2">{t(`landing.${s}_title`)}</h3>
                <p className="text-sm text-brand-muted leading-relaxed max-w-xs">{t(`landing.${s}_desc`)}</p>
              </RevealItem>
            ))}
          </div>
        </Reveal>
      </section>

      {/* CTA */}
      <section className="relative overflow-hidden py-20 bg-header">
        <HeroBackdrop />
        <Reveal className="relative max-w-2xl mx-auto px-6 text-center">
          <RevealItem>
            <h2 className="text-display text-3xl text-brand-dark mb-4 text-balance">{t("landing.cta_title")}</h2>
            <p className="text-fg-subtle mb-8">{t("landing.cta_sub", { count: FREE_REPORTS_ON_SIGNUP })}</p>
          </RevealItem>
          <RevealItem>
            <Button size="lg" asChild className="text-sm">
              <Link to={ctaPath}>{t("landing.cta_upload")}</Link>
            </Button>
          </RevealItem>
        </Reveal>
      </section>

      {/* First-visit orientation card. Landing only — inside the product the
          user has already decided what this is. */}
      <WelcomeCard />

      {/* Footer */}
      <footer className="py-8 border-t border-brand-border">
        <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-sm text-brand-muted">
          <div className="flex items-center gap-2">
            <BarChart2 size={15} className="text-accent-fg" />
            <span className="font-semibold text-brand-dark">ByteReport</span>
          </div>
          <span>{t("landing.footer", { year: new Date().getFullYear() })}</span>
        </div>
      </footer>
    </div>
  );
}
