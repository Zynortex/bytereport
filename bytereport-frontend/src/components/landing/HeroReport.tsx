import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { m, useInView } from "motion/react";
import { getDemo } from "@/data/demoReport";
import { useCountUp } from "@/lib/countUp";
import { useReducedMotion } from "@/lib/motion";
import { DUR, EASE, MS, REVEAL_OFFSET } from "@/lib/motionTokens";
import { formatCurrency, scoreColor, scoreZoneKey } from "@/lib/utils";

/**
 * The hero shows the product instead of describing it: a small live report
 * built from the demo report's own numbers — nothing invented here.
 *
 * On first view: the card fades up, the Health Score ring fills to the
 * score, three KPIs count up, and the weekly revenue line draws left to
 * right, all on the house curve. There is one demo business, so it plays
 * once (MS.heroCycle is the interval a second one would rotate on).
 *
 * No layout shift: every counting number reserves its final width, and only
 * opacity/transform/stroke animate.
 */

const VB_W = 320;
const VB_H = 88;

function linePath(values: number[]): { d: string; peak: [number, number] } {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i): [number, number] => [
    4 + (i * (VB_W - 8)) / (values.length - 1),
    VB_H - 6 - ((v - min) / span) * (VB_H - 14),
  ]);
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const peakIdx = values.indexOf(max);
  return { d, peak: pts[peakIdx] };
}

/** A number that counts up inside a box already sized for its final value. */
function Counting({ value, active, format, className }: {
  value: number; active: boolean; format: (n: number) => string; className?: string;
}) {
  const current = useCountUp(value, active, MS.count);
  return (
    <span className={`grid ${className ?? ""}`}>
      <span className="invisible col-start-1 row-start-1" aria-hidden="true">{format(value)}</span>
      <span className="col-start-1 row-start-1" aria-label={format(value)}>{format(Math.round(current))}</span>
    </span>
  );
}

export function HeroReport() {
  const { t, i18n } = useTranslation();
  const demo = getDemo(i18n.language);
  const reduced = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.35 });
  const go = inView || reduced;

  const { metrics, report, info } = demo;
  const score = report.financial_health_score.score;
  const zone = scoreZoneKey(score);
  const color = scoreColor(score);
  const money = (n: number) => formatCurrency(n, info.currency);
  const revenue = (report.weekly_cash_flow ?? []).map((w) => w.revenue);
  const { d, peak } = linePath(revenue);

  // Strokes: animated from zero, or drawn already when motion is reduced.
  const draw = (to: number, delay: number) => ({
    initial: reduced ? false as const : { pathLength: 0 },
    animate: go ? { pathLength: to } : undefined,
    transition: { duration: DUR.draw, ease: EASE, delay },
  });

  const R = 46;
  return (
    <m.div
      ref={ref}
      initial={{ opacity: 0, y: REVEAL_OFFSET }}
      animate={go ? { opacity: 1, y: 0 } : undefined}
      transition={{ duration: DUR.reveal, ease: EASE }}
      className="relative w-full max-w-[30rem] rounded-xs border border-brand-border bg-header p-5 sm:p-6"
      aria-label={t("landing.ex_eyebrow")}
    >
      <div className="flex items-baseline justify-between gap-3">
        <p className="label-caps text-[11px] text-accent-fg">{t("landing.ex_eyebrow")}</p>
        <span className="text-xs text-brand-muted">{t("landing.ex_period")}</span>
      </div>
      <p className="text-sm text-brand-dark mt-1 truncate">{info.name}</p>
      <span className="block w-8 h-px bg-accent mt-3 mb-5" aria-hidden="true" />

      <div className="flex items-center gap-5 sm:gap-6">
        {/* Health Score ring: a 2px stroke that fills to the score. */}
        <div className="relative shrink-0 w-[104px] h-[104px]">
          <svg viewBox="0 0 104 104" className="w-full h-full -rotate-90" aria-hidden="true">
            <circle cx="52" cy="52" r={R} fill="none" stroke="var(--color-line)" strokeWidth="2" />
            <m.circle cx="52" cy="52" r={R} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round"
              {...draw(score / 100, 0.1)} />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <Counting value={score} active={go} format={(n) => String(n)}
              className="text-score text-[34px] leading-none text-center" />
            <span className="label-caps text-[9px] mt-1.5" style={{ color }}>{t(`report.zone_${zone}`)}</span>
          </div>
        </div>

        <dl className="flex-1 min-w-0 space-y-2.5">
          {[
            ["landing.ex_revenue", metrics.total_revenue],
            ["landing.ex_expenses", metrics.total_expenses],
            ["landing.ex_profit", metrics.profit],
          ].map(([key, value]) => (
            <div key={key as string} className="flex items-baseline justify-between gap-3 border-b border-brand-border pb-2 last:border-0 last:pb-0">
              <dt className="text-xs text-brand-muted">{t(key as string)}</dt>
              <dd className="mono-num text-sm sm:text-base text-brand-dark text-right">
                <Counting value={value as number} active={go} format={money} />
              </dd>
            </div>
          ))}
        </dl>
      </div>

      {/* Weekly revenue, drawn left to right. */}
      <div className="mt-6">
        <div className="flex items-baseline justify-between mb-2">
          <span className="label-caps text-[10px] text-brand-muted">{t("landing.ex_revenue")}</span>
          <span className="text-[10px] text-brand-muted mono-num">{t("report.peak_week")}: {money(Math.max(...revenue))}</span>
        </div>
        <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="w-full h-auto" aria-hidden="true">
          <line x1="0" y1={VB_H - 1} x2={VB_W} y2={VB_H - 1} stroke="var(--color-line)" strokeWidth="1" />
          <m.path d={d} fill="none" stroke="var(--color-accent-fg)" strokeWidth="1.75"
            strokeLinejoin="round" strokeLinecap="round" {...draw(1, 0.25)} />
          <m.circle cx={peak[0]} cy={peak[1]} r="3" fill="var(--color-accent-fg)"
            initial={reduced ? false : { opacity: 0 }}
            animate={go ? { opacity: 1 } : undefined}
            transition={{ duration: DUR.hover, ease: EASE, delay: 0.25 + DUR.draw }} />
        </svg>
      </div>
    </m.div>
  );
}
