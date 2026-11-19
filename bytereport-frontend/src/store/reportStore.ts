import { create } from "zustand";
import { defaultLayout, normalizeLayout, type ReportLayout } from "@/lib/reportBlocks";
import { saveReport, loadReports, loadReport, renameReport as renameRemote, deleteReport as deleteRemote } from "@/api/db";
import type {
  ParseResult,
  FinancialMetrics,
  AIReport,
  BusinessInfo,
  ReportSummary,
} from "@/types";

interface ReportState {
  parseResult: ParseResult | null;
  metrics:     FinancialMetrics | null;
  report:      AIReport | null;
  businessInfo: BusinessInfo;
  history:     ReportSummary[];

  /**
   * Which sections the current report shows and in what order. Kept per
   * report in localStorage, keyed by the report's id, so an arrangement made
   * for one client is still there when that report is opened again — and is
   * not carried over to the next client's report by accident.
   */
  layout:      ReportLayout;

  /**
   * Rename / delete a saved report. The local copy always changes; the result
   * says whether the server copy did too (false = this device only, e.g. the
   * report was never saved remotely or the policies refuse the change).
   */
  renameReport: (id: string, name: string) => Promise<boolean>;
  deleteReport: (id: string) => Promise<boolean>;
  reportId:    string | null;
  setLayout:   (l: ReportLayout) => void;
  resetLayout: () => void;

  setParseResult:  (r: ParseResult) => void;
  setMetrics:      (m: FinancialMetrics) => void;
  setReport:       (r: AIReport) => void;
  setBusinessInfo: (info: Partial<BusinessInfo>) => void;

  /**
   * Persist the current report to Supabase + update local history.
   * Returns the DB-assigned report UUID, or null on failure.
   * Never throws — a save failure must not block the UI flow.
   */
  saveToSupabase: (userId: string) => Promise<string | null>;

  /**
   * Fetch a full report from Supabase by id and restore it into the store.
   * Returns true on success, false if the record wasn't found or fetch failed.
   */
  openReport: (reportId: string) => Promise<boolean>;

  /**
   * Load history for a user.
   * - With userId: fetches from Supabase and caches to localStorage.
   * - Without userId: reads from localStorage cache only.
   */
  loadHistory: (userId?: string) => Promise<void>;

  reset: () => void;
}

const DEFAULT_INFO: BusinessInfo = { name: "", type: "", period: "", currency: "UZS" };
const LS_KEY = "br_history";
const LAYOUT_KEY = (id: string | null) => `br_layout_${id ?? "draft"}`;

function readLayout(id: string | null): ReportLayout {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY(id));
    return raw ? normalizeLayout(JSON.parse(raw)) : defaultLayout();
  } catch {
    return defaultLayout();
  }
}

function writeLayout(id: string | null, layout: ReportLayout) {
  try { localStorage.setItem(LAYOUT_KEY(id), JSON.stringify(layout)); } catch { /* private mode */ }
}

function readLocalHistory(): ReportSummary[] {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function writeLocalHistory(list: ReportSummary[]) {
  localStorage.setItem(LS_KEY, JSON.stringify(list.slice(0, 20)));
}

export const useReportStore = create<ReportState>((set, get) => ({
  parseResult:  null,
  metrics:      null,
  report:       null,
  businessInfo: DEFAULT_INFO,
  history:      [],
  layout:       defaultLayout(),
  reportId:     null,

  setLayout: (layout) => {
    writeLayout(get().reportId, layout);
    set({ layout });
  },
  resetLayout: () => {
    const layout = defaultLayout();
    writeLayout(get().reportId, layout);
    set({ layout });
  },

  renameReport: async (id, name) => {
    const updated = get().history.map((r) => (r.id === id ? { ...r, business_name: name } : r));
    writeLocalHistory(updated);
    set({ history: updated });
    if (get().reportId === id) set((s) => ({ businessInfo: { ...s.businessInfo, name } }));
    return renameRemote(id, name);
  },

  deleteReport: async (id) => {
    const updated = get().history.filter((r) => r.id !== id);
    writeLocalHistory(updated);
    try { localStorage.removeItem(LAYOUT_KEY(id)); } catch { /* private mode */ }
    set({ history: updated });
    return deleteRemote(id);
  },

  setParseResult:  (r) => set({ parseResult: r }),
  setMetrics:      (m) => set({ metrics: m }),
  setReport:       (r) => set({ report: r, reportId: null, layout: readLayout(null) }),
  setBusinessInfo: (info) =>
    set((s) => ({ businessInfo: { ...s.businessInfo, ...info } })),

  saveToSupabase: async (userId) => {
    const { report, metrics, businessInfo, parseResult } = get();
    if (!report || !metrics) return null;

    const reportId = await saveReport(
      userId,
      businessInfo,
      metrics,
      report,
      parseResult?.transactions ?? []
    );

    // Build summary entry using the real DB id (fallback to UUID if save failed)
    const entry: ReportSummary = {
      id:            reportId ?? crypto.randomUUID(),
      business_name: businessInfo.name  || "Без названия",
      business_type: businessInfo.type  || "",
      period:        businessInfo.period || "",
      score:         report.financial_health_score.score,
      status:        report.financial_health_score.status,
      created_at:    new Date().toISOString(),
    };

    const updated = [entry, ...readLocalHistory()].slice(0, 20);
    writeLocalHistory(updated);
    const layout = get().layout;
    writeLayout(entry.id, layout);
    set({ history: updated, reportId: entry.id, layout });

    return reportId;
  },

  openReport: async (reportId) => {
    const full = await loadReport(reportId);
    if (!full) return false;
    set({
      metrics:      full.metrics,
      report:       full.report,
      businessInfo: full.businessInfo,
      parseResult:  null,   // transactions not needed for view-only
      reportId:     reportId,
      layout:       readLayout(reportId),
    });
    return true;
  },

  loadHistory: async (userId) => {
    if (userId) {
      const remote = await loadReports(userId);
      if (remote.length > 0) {
        writeLocalHistory(remote);
        set({ history: remote });
        return;
      }
    }
    // Fallback: localStorage cache
    set({ history: readLocalHistory() });
  },

  reset: () =>
    set({ parseResult: null, metrics: null, report: null, businessInfo: DEFAULT_INFO,
          layout: defaultLayout(), reportId: null }),
}));

// Development only: lets a browser-driven check seed a report into the store
// without a Supabase session. Stripped from production builds by Vite's
// dead-code elimination on import.meta.env.DEV.
if (import.meta.env.DEV) {
  (window as unknown as { __reportStore?: typeof useReportStore }).__reportStore = useReportStore;
}
