import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Loader2, Pencil, Trash2, X } from "lucide-react";
import { ScoreBadge } from "@/components/ui/ScoreBadge";
import { DeltaLabel } from "@/components/dashboard/ScoreTrend";
import { cn, scoreColor } from "@/lib/utils";
import type { ReportSummary } from "@/types";

interface Props {
  report: ReportSummary;
  /** Change against the previous report of the same business, or null. */
  delta: number | null;
  opening: boolean;
  disabled: boolean;
  last: boolean;
  onOpen: () => void;
  onRename: (name: string) => Promise<void>;
  onDelete: () => void;
}

const ICON_BTN =
  "h-11 w-11 md:h-9 md:w-9 flex items-center justify-center rounded-xs text-brand-muted " +
  "hover:text-brand-dark transition-colors duration-200 ease-out active:translate-y-px disabled:opacity-40";

/**
 * One saved report: open it, rename it, delete it.
 *
 * The row used to be a single <button>, which left nowhere to put the other
 * two actions — a button cannot contain buttons. Now the open area is one
 * control and the actions sit beside it, always visible: hover-only controls
 * do not exist on a phone.
 */
export function HistoryRow({ report: r, delta, opening, disabled, last, onOpen, onRename, onDelete }: Props) {
  const { t, i18n } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(r.business_name);
  const [saving, setSaving] = useState(false);
  const locale = i18n.language === "en" ? "en-US" : "ru-RU";

  const save = async () => {
    const next = name.trim();
    if (!next || next === r.business_name) { setEditing(false); setName(r.business_name); return; }
    setSaving(true);
    await onRename(next);
    setSaving(false);
    setEditing(false);
  };

  const scoreBox = (
    <div
      // Outline + coloured numeral rather than a solid block: a saturated fill
      // is the loudest element on a dark ground.
      className="w-10 h-10 rounded-xs border flex items-center justify-center text-sm shrink-0 text-score"
      style={{ color: scoreColor(r.score), borderColor: `${scoreColor(r.score)}66` }}
    >
      {opening ? <Loader2 size={16} className="animate-spin" /> : r.score}
    </div>
  );

  const meta = (
    <p className="text-xs text-brand-muted">
      {r.business_type && `${r.business_type} · `}
      {r.period && `${r.period} · `}
      {new Date(r.created_at).toLocaleDateString(locale)}
    </p>
  );

  return (
    <div className={cn("flex items-center gap-2 py-2.5", !last && "border-b border-brand-border")}>
      {editing ? (
        <form
          className="flex-1 min-w-0 flex items-center gap-3"
          onSubmit={(e) => { e.preventDefault(); save(); }}
        >
          {scoreBox}
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Escape") { setEditing(false); setName(r.business_name); } }}
            aria-label={t("dashboard.name_placeholder")}
            placeholder={t("dashboard.name_placeholder")}
            className="flex-1 min-w-0 h-11 md:h-9 rounded-xs border border-brand-border bg-transparent px-3 text-sm text-brand-dark transition-[border-color] duration-200 ease-out focus:outline-none focus:border-accent-fg focus:ring-2 focus:ring-accent/30"
          />
          <button type="submit" disabled={saving} aria-label={t("dashboard.save")} className={ICON_BTN}>
            {saving ? <Loader2 size={15} className="animate-spin" /> : <Check size={16} />}
          </button>
          <button
            type="button"
            onClick={() => { setEditing(false); setName(r.business_name); }}
            aria-label={t("dashboard.cancel")}
            className={ICON_BTN}
          >
            <X size={16} />
          </button>
        </form>
      ) : (
        <>
          <button
            type="button"
            onClick={onOpen}
            disabled={disabled}
            className="flex-1 min-w-0 flex items-center gap-3 sm:gap-4 min-h-11 px-1 py-1 text-left rounded-xs transition-colors duration-200 ease-out hover:bg-ground active:bg-line/60 disabled:opacity-60"
          >
            {scoreBox}
            <div className="min-w-0">
              <p className="text-sm font-semibold text-brand-dark break-words">{r.business_name}</p>
              {meta}
            </div>
          </button>
          <div className="hidden sm:flex flex-col items-end gap-1 shrink-0">
            {/* Derived live from r.score — the stored status text is ignored. */}
            <ScoreBadge score={r.score} />
            {delta !== null && <DeltaLabel delta={delta} />}
          </div>
          <div className="flex shrink-0">
            <button type="button" onClick={() => setEditing(true)} disabled={disabled} aria-label={t("dashboard.rename")} title={t("dashboard.rename")} className={ICON_BTN}>
              <Pencil size={15} />
            </button>
            <button type="button" onClick={onDelete} disabled={disabled} aria-label={t("dashboard.delete")} title={t("dashboard.delete")} className={cn(ICON_BTN, "hover:text-sev-high-fg")}>
              <Trash2 size={15} />
            </button>
          </div>
        </>
      )}
    </div>
  );
}
