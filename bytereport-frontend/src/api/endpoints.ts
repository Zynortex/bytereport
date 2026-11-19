import { apiClient } from "./client";
import i18n from "@/i18n";
import type { ReportLayout } from "@/lib/reportBlocks";
import type {
  ParseResult,
  Transaction,
  FinancialMetrics,
  AIReport,
  BusinessInfo,
  ChatMessage,
  CashflowForecast,
  Credits,
  DraftTransaction,
  ParseNoteResponse,
  TranscriptionResponse,
} from "@/types";

export const api = {
  async uploadCSV(file: File): Promise<ParseResult> {
    const form = new FormData();
    form.append("file", file);
    const { data } = await apiClient.post<ParseResult>("/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  async analyzeTransactions(
    transactions: Transaction[],
    closingBalance?: number | null
  ): Promise<FinancialMetrics> {
    const { data } = await apiClient.post<FinancialMetrics>("/analyze", {
      transactions,
      closing_balance: closingBalance ?? null,
    });
    return data;
  },

  /** Cash forecast only, from a balance the user adds later. No AI, no credit. */
  async recomputeForecast(metrics: FinancialMetrics, closingBalance: number): Promise<CashflowForecast> {
    const { data } = await apiClient.post<CashflowForecast>("/analyze/forecast", {
      weekly_breakdown: metrics.weekly_breakdown ?? [],
      period_end: metrics.period_end,
      closing_balance: closingBalance,
    });
    return data;
  },

  /** Reports left on this account; the first call also pays the signup bonus. */
  async getCredits(): Promise<Credits> {
    const { data } = await apiClient.get<Credits>("/account/credits");
    return data;
  },

  async generateAIReport(
    metrics: FinancialMetrics,
    info: BusinessInfo
  ): Promise<AIReport> {
    const { data } = await apiClient.post<AIReport>("/report/analyze", {
      metrics,
      business_name: info.name,
      business_type: info.type,
      currency: info.currency,
      language: i18n.language || "ru",
    });
    return data;
  },

  async downloadPDF(
    report: AIReport,
    info: BusinessInfo,
    metrics?: FinancialMetrics | null,
    // Which sections, in what order. The PDF is built from this — not from
    // an order of its own — so what the accountant arranged is what ships.
    layout?: ReportLayout | null
  ): Promise<Blob> {
    const { data } = await apiClient.post(
      "/report/pdf",
      {
        report,
        business_name: info.name,
        business_type: info.type,
        period: info.period,
        // Source data for the PDF charts. Without it the backend renders the
        // report text-only — it has no other way to reach these numbers.
        metrics: metrics ?? undefined,
        language: i18n.language || "ru",
        layout: layout ?? undefined,
      },
      { responseType: "blob" }
    );
    return data;
  },

  async sendChatMessage(
    message: string,
    history: ChatMessage[],
    metrics: object,
    report: object | null,
    info: BusinessInfo
  ): Promise<string> {
    const { data } = await apiClient.post<{ answer: string }>("/chat", {
      message,
      history,
      metrics,
      ai_report: report,
      business_name: info.name,
      business_type: info.type,
      currency: info.currency,
    });
    return data.answer;
  },

  // ── Voice / free-text note ───────────────────────────────────────────────

  async transcribeNote(audio: Blob, language?: string): Promise<TranscriptionResponse> {
    const form = new FormData();
    // The filename matters: the backend infers the audio container from it.
    form.append("file", audio, `note.${audio.type.includes("mp4") ? "mp4" : "webm"}`);
    if (language) form.append("language", language);
    const { data } = await apiClient.post<TranscriptionResponse>("/voice/transcribe", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  async parseNote(text: string, currency: string): Promise<ParseNoteResponse> {
    const { data } = await apiClient.post<ParseNoteResponse>("/voice/parse", {
      text,
      currency,
      language: i18n.language || "ru",
    });
    return data;
  },

  /** Photo of a receipt or a handwritten note -> the same draft rows. */
  async parsePhoto(image: File, currency: string): Promise<ParseNoteResponse> {
    const form = new FormData();
    form.append("file", image);
    form.append("currency", currency);
    form.append("language", i18n.language || "ru");
    const { data } = await apiClient.post<ParseNoteResponse>("/voice/photo", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  },

  /**
   * Confirmed rows -> workbook. There is no endpoint from raw text to a file:
   * the only input this accepts is rows a human has already seen.
   */
  async downloadNoteExcel(
    transactions: DraftTransaction[],
    businessName: string,
    currency: string
  ): Promise<Blob> {
    const { data } = await apiClient.post(
      "/voice/excel",
      {
        transactions,
        business_name: businessName,
        currency,
        language: i18n.language || "ru",
      },
      { responseType: "blob" }
    );
    return data;
  },
};
