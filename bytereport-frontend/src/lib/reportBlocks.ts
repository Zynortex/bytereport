/**
 * The report's sections and the layout that arranges them.
 *
 * The registry is repo-root report-blocks.json, the same file the PDF
 * generator reads — so a block the web can arrange is a block the PDF can
 * place, by construction. Array order in the file is the default order on
 * both surfaces.
 */
import registry from "../../../report-blocks.json";

export type BlockKind = "text" | "chart" | "list" | "metrics";

export interface BlockDef {
  id: string;
  kind: BlockKind;
  label: Record<string, string>;
  /** Field on AIReport whose entries can be hidden one at a time. */
  items?: string;
  /** false for sections that exist only on the web (the KPI strip). */
  pdf?: boolean;
}

export const BLOCKS: BlockDef[] = registry.blocks as BlockDef[];
export const BLOCK_IDS: string[] = BLOCKS.map((b) => b.id);
const BY_ID = new Map(BLOCKS.map((b) => [b.id, b]));

export function blockDef(id: string): BlockDef | undefined {
  return BY_ID.get(id);
}

export function blockLabel(id: string, lang: string): string {
  const def = BY_ID.get(id);
  return def?.label[lang] ?? def?.label.ru ?? id;
}

export interface LayoutBlock {
  id: string;
  visible: boolean;
}

/** Mirrors ReportLayout in app/services/report_layout.py. */
export interface ReportLayout {
  blocks: LayoutBlock[];
  hidden_items: Record<string, number[]>;
}

export function defaultLayout(): ReportLayout {
  return { blocks: BLOCK_IDS.map((id) => ({ id, visible: true })), hidden_items: {} };
}

/**
 * Bring a stored layout up to date with the registry: drop ids that no longer
 * exist, append new sections HIDDEN so they surface where the accountant can
 * find them rather than silently appearing mid-report, and dedupe.
 */
export function normalizeLayout(raw: Partial<ReportLayout> | null | undefined): ReportLayout {
  const seen = new Set<string>();
  const blocks: LayoutBlock[] = [];
  for (const b of raw?.blocks ?? []) {
    if (!b || typeof b.id !== "string" || !BY_ID.has(b.id) || seen.has(b.id)) continue;
    seen.add(b.id);
    blocks.push({ id: b.id, visible: b.visible !== false });
  }
  for (const id of BLOCK_IDS) {
    if (!seen.has(id)) blocks.push({ id, visible: blocks.length === 0 });
  }
  // A layout with no known blocks at all is not "everything hidden"; it is the
  // default.
  if (!raw?.blocks?.length) return defaultLayout();

  const hidden_items: Record<string, number[]> = {};
  for (const [id, idxs] of Object.entries(raw?.hidden_items ?? {})) {
    const def = BY_ID.get(id);
    if (!def?.items || !Array.isArray(idxs)) continue;
    hidden_items[id] = [...new Set(idxs.map(Number).filter((n) => Number.isInteger(n) && n >= 0))].sort((a, b) => a - b);
  }
  return { blocks, hidden_items };
}

export function isDefaultLayout(layout: ReportLayout): boolean {
  const d = defaultLayout();
  return (
    layout.blocks.length === d.blocks.length &&
    layout.blocks.every((b, i) => b.id === d.blocks[i].id && b.visible) &&
    Object.values(layout.hidden_items).every((v) => v.length === 0)
  );
}

export function moveBlock(layout: ReportLayout, from: number, to: number): ReportLayout {
  if (from === to || from < 0 || to < 0 || from >= layout.blocks.length || to >= layout.blocks.length) return layout;
  const blocks = [...layout.blocks];
  const [moved] = blocks.splice(from, 1);
  blocks.splice(to, 0, moved);
  return { ...layout, blocks };
}

export function setVisible(layout: ReportLayout, id: string, visible: boolean): ReportLayout {
  return { ...layout, blocks: layout.blocks.map((b) => (b.id === id ? { ...b, visible } : b)) };
}

export function toggleItem(layout: ReportLayout, id: string, index: number): ReportLayout {
  const current = new Set(layout.hidden_items[id] ?? []);
  if (current.has(index)) current.delete(index);
  else current.add(index);
  return { ...layout, hidden_items: { ...layout.hidden_items, [id]: [...current].sort((a, b) => a - b) } };
}

export function keepItems<T>(layout: ReportLayout, id: string, items: T[]): T[] {
  const hidden = new Set(layout.hidden_items[id] ?? []);
  return items.filter((_, i) => !hidden.has(i));
}

// ── Templates: a saved arrangement, reused across clients ──────────────────
//
// Stored per browser. An accountant who arranges the same report for many
// clients should not redo it each time; a template is that arrangement under
// a name. localStorage rather than a table, because the brief marked this as
// a lightweight addition and the arrangement is the accountant's own working
// preference, not client data.

const TEMPLATES_KEY = "br_layout_templates";

export interface LayoutTemplate {
  name: string;
  layout: ReportLayout;
  saved_at: string;
}

export function loadTemplates(): LayoutTemplate[] {
  try {
    const raw = JSON.parse(localStorage.getItem(TEMPLATES_KEY) ?? "[]");
    return Array.isArray(raw)
      ? raw.filter((t) => t && typeof t.name === "string").map((t) => ({ ...t, layout: normalizeLayout(t.layout) }))
      : [];
  } catch {
    return [];
  }
}

export function saveTemplate(name: string, layout: ReportLayout): LayoutTemplate[] {
  const trimmed = name.trim();
  if (!trimmed) return loadTemplates();
  const rest = loadTemplates().filter((t) => t.name !== trimmed);
  const next = [{ name: trimmed, layout, saved_at: new Date().toISOString() }, ...rest].slice(0, 20);
  try { localStorage.setItem(TEMPLATES_KEY, JSON.stringify(next)); } catch { /* quota or private mode */ }
  return next;
}

export function deleteTemplate(name: string): LayoutTemplate[] {
  const next = loadTemplates().filter((t) => t.name !== name);
  try { localStorage.setItem(TEMPLATES_KEY, JSON.stringify(next)); } catch { /* nothing to do */ }
  return next;
}
