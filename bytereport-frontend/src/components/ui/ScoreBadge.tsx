import { useTranslation } from "react-i18next";
import { cn, scoreColor, scoreZoneKey } from "@/lib/utils";

interface Props {
  score: number;
  className?: string;
}

/**
 * Status pill for a health score.
 *
 * Both the label and the colour are derived from `score` on every render — the
 * status string stored alongside a report in the database is deliberately
 * ignored. Older rows were written under a retired 5-zone system ("Сильное"),
 * so trusting stored text made two reports with near-identical scores render
 * different words in different colours. Deriving live means the whole history
 * is consistent no matter when a row was created.
 */
export function ScoreBadge({ score, className }: Props) {
  const { t } = useTranslation();
  const color = scoreColor(score);
  const label = t(`report.zone_${scoreZoneKey(score)}`);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-xs border px-2 py-1",
        "label-caps text-[10px] whitespace-nowrap",
        className
      )}
      style={{
        color,
        borderColor: `${color}55`,
        backgroundColor: "transparent",
      }}
    >
      <span className="w-[3px] h-3 shrink-0" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}
