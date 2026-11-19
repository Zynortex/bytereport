import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown } from "lucide-react";
import { Card } from "@/components/ui/card";
import { ScoreCounter } from "@/components/ui/ScoreCounter";
import { cn, scoreColor, scoreZoneKey } from "@/lib/utils";
import { breakdownLines, formatPoints, wasCapped } from "@/lib/scoreBreakdown";
import type { HealthBreakdownItem, HealthScore } from "@/types";

interface Props {
  score: HealthScore;
  /** The engine's five checks; omitted for reports saved before it kept them. */
  breakdown?: HealthBreakdownItem[];
}

/**
 * Health Score as an instrument reading, not a gauge.
 *
 * The circular progress ring is gone: a ring plus a coloured capsule reads as a
 * game achievement, which is the wrong register for a finance tool. What remains
 * is the figure itself — large, monospaced — an uppercase status, and a single
 * accent hairline.
 */
export function HealthScoreCard({ score, breakdown }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const lines = breakdown?.length ? breakdownLines(breakdown, t) : [];
  const color = scoreColor(score.score);
  // Derived from the number, not from score.status — a report saved under the
  // retired 5-zone system carries stale text ("Сильное") that would otherwise
  // contradict the badge shown for the same report in the history list.
  const statusLabel = t(`report.zone_${scoreZoneKey(score.score)}`);

  return (
    <Card className="flex flex-col py-8 px-6">
      <p className="label-caps text-[11px] text-brand-muted">
        {t("report.health_score_title")}
      </p>
      <span className="block w-8 h-px bg-accent mt-3 mb-7" aria-hidden="true" />

      <div className="flex items-baseline gap-3">
        {/* Counts 0 -> score on mount. The figure is tabular-nums (.text-score)
            so the digits do not jitter while it runs, and ScoreCounter jumps
            straight to the final value under reduced motion. */}
        <ScoreCounter
          value={score.score}
          duration={1100}
          className="text-score text-[64px] leading-none"
          style={{ color }}
        />
        <span className="text-brand-muted text-sm mono-num">/ 100</span>
      </div>

      <p className="label-caps text-xs mt-4" style={{ color }}>
        {statusLabel}
      </p>
      {/* The zone reads as a verdict on its own. This says what it is drawn
          from — a cash-flow signal, not an audit. Same text as the PDF, from
          the shared report-copy.json. */}
      <p className="text-[11px] text-brand-muted mt-1.5 leading-snug">
        {t("score.caption")}
      </p>

      {/* Zone scale: four flat segments, no pill, no rounding. Widths mirror the
          backend thresholds exactly (critical 0-39 / unstable 40-54 /
          stable 55-69 / excellent 70-100). */}
      <div className="w-full mt-7">
        <div className="relative h-1 flex">
          <div style={{ width: "40%" }} className="bg-danger/40" />
          <div style={{ width: "15%" }} className="bg-warning/40" />
          <div style={{ width: "15%" }} className="bg-success/25" />
          <div style={{ width: "30%" }} className="bg-success/45" />
          <div
            className="absolute top-[-3px] h-[7px] w-[2px] bg-brand-dark -translate-x-1/2"
            style={{ left: `${Math.min(Math.max(score.score, 1), 99)}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] mt-2 text-brand-muted">
          <span>{t("report.zone_critical")}</span>
          <span>{t("report.zone_unstable")}</span>
          <span>{t("report.zone_stable")}</span>
          <span>{t("report.zone_strong")}</span>
        </div>
      </div>

      {/* How the number was built — the engine's own arithmetic, one line per
          check. Collapsed by default: the number leads, the working is one
          tap away. Same sentences as the PDF (report-copy.json). */}
      {lines.length > 0 && (
        <div className="mt-6 border-t border-brand-border">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-controls="score-breakdown"
            className="w-full flex items-center justify-between gap-3 min-h-11 pt-3 text-left text-xs label-caps text-brand-muted hover:text-brand-dark transition-colors duration-200 ease-out"
          >
            {t("score_breakdown.title")}
            <ChevronDown size={14} className={cn("shrink-0 transition-transform duration-200 ease-out", open && "rotate-180")} />
          </button>
          {open && (
            <div id="score-breakdown" className="pt-2 anim-fade-in">
              <p className="text-xs text-brand-muted mb-3">
                {t("score_breakdown.intro").replace("{score}", String(score.score))}
              </p>
              <ul className="space-y-2.5">
                {lines.map((line, i) => (
                  <li key={i} className="flex gap-3 text-xs leading-snug">
                    <span className={cn("mono-num w-9 shrink-0 text-right", line.points ? "text-brand-dark" : "text-brand-muted")}>
                      {formatPoints(line.points)}
                    </span>
                    <span className="text-fg-subtle">{line.text}</span>
                  </li>
                ))}
              </ul>
              {wasCapped(breakdown!) && (
                <p className="text-xs text-brand-muted mt-3">{t("score_breakdown.capped")}</p>
              )}
            </div>
          )}
        </div>
      )}

      <p className="text-sm text-brand-muted leading-relaxed mt-7">{score.reasoning}</p>

      {/* Scope, inside the card rather than in a footer. A statement-based
          analysis cannot see receivables, payables, cash outside the account
          or accruals — that is its coverage, and it belongs next to the number
          it qualifies. */}
      <div className="mt-6 pt-4 border-t border-brand-border">
        <p className="label-caps text-[10px] text-brand-muted mb-1.5">{t("score.scope_title")}</p>
        <p className="text-xs text-fg-subtle leading-relaxed">{t("score.scope")}</p>
      </div>
    </Card>
  );
}
