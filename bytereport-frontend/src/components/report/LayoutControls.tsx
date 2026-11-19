import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowDown, ArrowUp, Eye, EyeOff, GripVertical, LayoutTemplate as LayoutIcon, RotateCcw, Save, Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  blockLabel, deleteTemplate, isDefaultLayout, loadTemplates, saveTemplate,
  type LayoutTemplate, type ReportLayout,
} from "@/lib/reportBlocks";
import { useExitAnimation } from "@/lib/motion";

// ── The frame around every section while customising ──────────────────────

interface FrameProps {
  id: string;
  index: number;
  count: number;
  visible: boolean;
  editing: boolean;
  /** Titles of the section's entries, for per-item hiding. */
  items?: string[];
  hiddenItems?: number[];
  onToggle: (id: string, visible: boolean) => void;
  onMove: (from: number, to: number) => void;
  onToggleItem?: (id: string, index: number) => void;
  children: React.ReactNode;
}

/**
 * Wraps one report section.
 *
 * Out of edit mode it renders nothing of its own — the section looks exactly
 * as it always has. In edit mode it adds a handle bar: drag to reorder, arrows
 * for the keyboard, an eye to hide, and for list sections a per-entry list so
 * the one insight that is wrong for this client can be switched off without
 * losing the other four.
 *
 * Native HTML5 drag events, no library: the list is short and the contract is
 * simple (an index moves to another index).
 */
// Dragging needs a precise pointer. On a touch screen HTML5 drag-and-drop
// barely works and fights the page scroll, so there the arrows are the way
// to reorder (they are always present).
const CAN_DRAG = typeof window !== "undefined" && window.matchMedia?.("(pointer: fine)").matches;

const FRAME_BTN = "p-1 max-md:h-11 max-md:w-11 max-md:flex max-md:items-center max-md:justify-center rounded-xs";

export function BlockFrame({
  id, index, count, visible, editing, items, hiddenItems = [],
  onToggle, onMove, onToggleItem, children,
}: FrameProps) {
  const { t, i18n } = useTranslation();
  const [over, setOver] = useState(false);
  const [showItems, setShowItems] = useState(false);

  if (!editing) {
    return visible ? <>{children}</> : null;
  }

  const label = blockLabel(id, i18n.language);
  const hiddenCount = hiddenItems.length;

  return (
    <div
      draggable={CAN_DRAG}
      onDragStart={(e) => { e.dataTransfer.setData("text/plain", String(index)); e.dataTransfer.effectAllowed = "move"; }}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault(); setOver(false);
        const from = Number(e.dataTransfer.getData("text/plain"));
        if (!Number.isNaN(from)) onMove(from, index);
      }}
      className={cn(
        "rounded-xs border transition-colors duration-200 ease-out",
        over ? "border-accent-fg" : "border-accent/40",
        !visible && "opacity-60"
      )}
    >
      <div className="flex items-center gap-2 px-3 py-2 bg-header border-b border-brand-border">
        {CAN_DRAG && <GripVertical size={14} className="text-brand-muted cursor-grab shrink-0" aria-hidden="true" />}
        <span className="label-caps text-[11px] text-brand-muted flex-1 min-w-0 md:truncate">{label}</span>

        {items && items.length > 0 && onToggleItem && (
          <button
            type="button"
            onClick={() => setShowItems((v) => !v)}
            className="text-[11px] text-brand-muted hover:text-brand-dark transition-colors duration-200 ease-out px-2 py-1 max-md:min-h-11 rounded-xs border border-brand-border"
          >
            {t("layout.items", { shown: items.length - hiddenCount, total: items.length })}
          </button>
        )}

        <button type="button" onClick={() => onMove(index, index - 1)} disabled={index === 0}
          aria-label={t("layout.move_up")}
          className={`${FRAME_BTN} text-brand-muted hover:text-brand-dark disabled:opacity-30 transition-colors duration-200 ease-out active:translate-y-px`}>
          <ArrowUp size={14} />
        </button>
        <button type="button" onClick={() => onMove(index, index + 1)} disabled={index === count - 1}
          aria-label={t("layout.move_down")}
          className={`${FRAME_BTN} text-brand-muted hover:text-brand-dark disabled:opacity-30 transition-colors duration-200 ease-out active:translate-y-px`}>
          <ArrowDown size={14} />
        </button>
        <button type="button" onClick={() => onToggle(id, !visible)}
          aria-label={visible ? t("layout.hide") : t("layout.show")} aria-pressed={!visible}
          className={cn(FRAME_BTN, "transition-colors duration-200 ease-out active:translate-y-px",
            visible ? "text-brand-muted hover:text-brand-dark" : "text-sev-medium-fg")}>
          {visible ? <Eye size={14} /> : <EyeOff size={14} />}
        </button>
      </div>

      {showItems && items && onToggleItem && (
        <ul className="px-3 py-2 border-b border-brand-border bg-ground/60 space-y-1 anim-fade-in">
          {items.map((title, i) => {
            const hidden = hiddenItems.includes(i);
            return (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => onToggleItem(id, i)}
                  className={cn(
                    "w-full flex items-center gap-2 text-left text-xs px-2 py-1 max-md:min-h-11 rounded-xs transition-colors duration-200 ease-out",
                    hidden ? "text-brand-muted line-through" : "text-brand-dark hover:bg-line/40"
                  )}
                >
                  {hidden ? <EyeOff size={12} className="shrink-0" /> : <Eye size={12} className="shrink-0 text-accent-fg" />}
                  <span className="truncate">{title}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {/* A hidden section keeps its content while editing so it can be found
          and switched back on; the dimming above marks it. */}
      <div className={cn(!visible && "pointer-events-none select-none")}>{children}</div>
    </div>
  );
}

// ── The toolbar: enter/leave edit mode, reset, templates ──────────────────

interface BarProps {
  editing: boolean;
  layout: ReportLayout;
  onEdit: (on: boolean) => void;
  onReset: () => void;
  onApply: (layout: ReportLayout) => void;
}

export function LayoutBar({ editing, layout, onEdit, onReset, onApply }: BarProps) {
  const { t } = useTranslation();
  const [templates, setTemplates] = useState<LayoutTemplate[]>([]);
  const [menu, setMenu] = useState(false);
  const [name, setName] = useState("");
  const { mounted, closing } = useExitAnimation(menu, 150);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => { setTemplates(loadTemplates()); }, [editing]);

  useEffect(() => {
    if (!menu) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setMenu(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [menu]);

  const customised = !isDefaultLayout(layout);

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <Button size="sm" variant={editing ? "default" : "outline"} onClick={() => onEdit(!editing)}>
        <LayoutIcon size={13} />
        {editing ? t("layout.done") : t("layout.customize")}
      </Button>

      {editing && (
        <>
          <Button size="sm" variant="ghost" onClick={onReset} disabled={!customised}>
            <RotateCcw size={13} />
            {t("layout.reset")}
          </Button>

          <div ref={ref} className="relative">
            <Button size="sm" variant="ghost" onClick={() => setMenu((v) => !v)}>
              <Save size={13} />
              {t("layout.templates")}
            </Button>
            {mounted && (
              <div className={cn(
                "absolute left-0 top-full mt-1.5 w-72 bg-header border border-brand-border rounded-xs p-3 z-40 origin-top-left",
                closing ? "anim-pop-out" : "anim-pop-in"
              )}>
                <div className="flex gap-2">
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder={t("layout.template_name")}
                    className="flex-1 min-w-0 rounded-xs border border-brand-border bg-transparent px-2 py-1.5 text-xs text-brand-dark placeholder:text-fg-subtle transition-[border-color] duration-200 ease-out focus:outline-none focus:border-accent-fg focus:ring-2 focus:ring-accent/30"
                    onKeyDown={(e) => { if (e.key === "Enter" && name.trim()) { setTemplates(saveTemplate(name, layout)); setName(""); } }}
                  />
                  <Button size="sm" onClick={() => { setTemplates(saveTemplate(name, layout)); setName(""); }} disabled={!name.trim()}>
                    {t("layout.save")}
                  </Button>
                </div>

                {templates.length > 0 ? (
                  <ul className="mt-3 space-y-1">
                    {templates.map((tpl) => (
                      <li key={tpl.name} className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => { onApply(tpl.layout); setMenu(false); }}
                          className="flex-1 text-left text-xs px-2 py-1.5 rounded-xs text-brand-dark hover:bg-line/40 transition-colors duration-200 ease-out truncate"
                        >
                          {tpl.name}
                        </button>
                        <button
                          type="button"
                          onClick={() => setTemplates(deleteTemplate(tpl.name))}
                          aria-label={t("layout.delete_template")}
                          className="p-1 rounded-xs text-brand-muted hover:text-sev-high-fg transition-colors duration-200 ease-out"
                        >
                          <Trash2 size={12} />
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-3 text-[11px] text-brand-muted leading-snug">{t("layout.no_templates")}</p>
                )}
              </div>
            )}
          </div>
        </>
      )}

      {!editing && customised && (
        <span className="text-[11px] text-brand-muted">{t("layout.customised_note")}</span>
      )}
    </div>
  );
}
