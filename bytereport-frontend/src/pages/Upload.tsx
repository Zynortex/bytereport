import { useState, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useDropzone } from "react-dropzone";
import { useTranslation } from "react-i18next";
import { Upload, FileSpreadsheet, CheckCircle, Loader2, AlertCircle, ChevronRight, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { useReportStore } from "@/store/reportStore";
import { useAuthStore } from "@/store/authStore";
import { api } from "@/api/endpoints";
import { ApiError, parseApiError } from "@/api/client";
import { exhaustedKey, isOutOfReports, useCreditsStore } from "@/store/creditsStore";
import { parseAmount } from "@/components/report/CashForecastCard";
import { AnalysisWait } from "@/components/upload/AnalysisWait";
import { ExportHelp } from "@/components/upload/ExportHelp";
import type { FinancialMetrics } from "@/types";

const SAMPLE_CSV = `date,amount,type,category,description
2024-01-03,68000,income,sales,Выручка касса — четверг
2024-01-04,91000,income,sales,Выручка касса — пятница
2024-01-05,104000,income,sales,Выручка касса — суббота
2024-01-06,97000,income,sales,Выручка касса — воскресенье
2024-01-07,62000,income,sales,Выручка касса — понедельник
2024-01-08,58000,income,sales,Выручка касса — вторник
2024-01-10,87000,income,sales,Доставка Яндекс Еда январь ч.1
2024-01-12,14500,expense,inventory,Закупка продуктов — мясо рыба
2024-01-14,8900,expense,inventory,Закупка продуктов — овощи зелень
2024-01-15,120000,expense,payroll,Зарплата персонал январь
2024-01-15,65000,expense,rent,Аренда помещения январь
2024-01-17,74000,income,sales,Выручка касса — среда
2024-01-18,88000,income,sales,Выручка касса — четверг
2024-01-19,112000,income,sales,Выручка касса — пятница
2024-01-20,7200,expense,utilities,Электричество вода январь
2024-01-22,43000,income,sales,Доставка Яндекс Еда январь ч.2
2024-01-25,6800,expense,marketing,Реклама ВКонтакте январь
2024-01-28,11200,expense,inventory,Закупка продуктов — бакалея
2024-01-31,9500,expense,software,Iiko лицензия касса
2024-02-01,71000,income,sales,Выручка касса — четверг
2024-02-02,94000,income,sales,Выручка касса — пятница
2024-02-03,108000,income,sales,Выручка касса — суббота
2024-02-04,99000,income,sales,Выручка касса — воскресенье
2024-02-07,63000,income,sales,Выручка касса — среда
2024-02-09,52000,income,sales,Доставка Яндекс Еда февраль ч.1
2024-02-10,16800,expense,inventory,Закупка продуктов — мясо рыба
2024-02-12,9400,expense,inventory,Закупка продуктов — овощи молочка
2024-02-14,28000,expense,marketing,Реклама День Святого Валентина
2024-02-15,120000,expense,payroll,Зарплата персонал февраль
2024-02-15,65000,expense,rent,Аренда помещения февраль
2024-02-16,89000,income,sales,Выручка касса — пятница
2024-02-17,118000,income,sales,Выручка касса — суббота
2024-02-19,7400,expense,utilities,Электричество вода февраль
2024-02-22,48000,income,sales,Доставка Яндекс Еда февраль ч.2
2024-02-26,12100,expense,inventory,Закупка продуктов — бакалея напитки
2024-02-29,9500,expense,software,Iiko лицензия касса
2024-03-01,76000,income,sales,Выручка касса — пятница
2024-03-02,115000,income,sales,Выручка касса — суббота
2024-03-03,107000,income,sales,Выручка касса — воскресенье
2024-03-07,69000,income,sales,Выручка касса — четверг
2024-03-08,96000,income,sales,Выручка 8 марта суббота
2024-03-09,58000,income,sales,Доставка Яндекс Еда март ч.1
2024-03-11,18200,expense,inventory,Закупка продуктов — мясо рыба
2024-03-12,10100,expense,inventory,Закупка продуктов — овощи зелень
2024-03-14,7800,expense,marketing,Реклама ВКонтакте март
2024-03-15,130000,expense,payroll,Зарплата персонал март + премия
2024-03-15,65000,expense,rent,Аренда помещения март
2024-03-18,8100,expense,utilities,Электричество вода март
2024-03-20,84000,income,sales,Выручка касса — среда
2024-03-22,71000,income,sales,Доставка Яндекс Еда март ч.2
2024-03-25,13900,expense,inventory,Закупка продуктов — бакалея
2024-03-28,22000,expense,equipment,Ремонт кофемашины
2024-03-29,9500,expense,software,Iiko лицензия касса
`;

function downloadSampleCSV() {
  const blob = new Blob([SAMPLE_CSV], { type: "text/csv;charset=utf-8;" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = "bytereport_sample_cafe.csv";
  a.click();
  URL.revokeObjectURL(url);
}

type Step = 0 | 1 | 2;

interface ProcessingStep { label: string; done: boolean; active: boolean; }

export default function UploadPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { setParseResult, setMetrics, setReport, setBusinessInfo, businessInfo, saveToSupabase } = useReportStore();
  const { user } = useAuthStore();

  const STEPS = [t("upload.step_upload"), t("upload.step_settings"), t("upload.step_analysis")];
  const BUSINESS_TYPES = t("business_types", { returnObjects: true }) as string[];

  const [step, setStep] = useState<Step>(0);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The balance ran out: the way forward is the pricing page, not "retry".
  const [outOfReports, setOutOfReports] = useState(false);
  const { credits, load: loadCredits } = useCreditsStore();
  // Typed text, kept separately so "12 500 000" can be typed with spaces; the
  // parsed number goes to businessInfo.
  const [balanceText, setBalanceText] = useState(
    businessInfo.closing_balance != null ? String(businessInfo.closing_balance) : ""
  );
  const balanceInvalid = balanceText.trim() !== "" && parseAmount(balanceText) === null;
  useEffect(() => { loadCredits(); }, [loadCredits]);
  // Seconds since the run started. This is real elapsed time, not a simulated
  // progress estimate — the AI call legitimately varies between ~15s and ~140s,
  // so the user gets an honest clock instead of a bar that guesses.
  const [elapsed, setElapsed] = useState(0);
  // When the AI call started (ms), for the countdown; and the user's figures,
  // computed before that call and shown while it runs.
  const [aiStartedAt, setAiStartedAt] = useState<number | null>(null);
  const [computed, setComputed] = useState<FinancialMetrics | null>(null);

  const makeProcessingSteps = (): ProcessingStep[] => [
    { label: t("upload.step_csv"),     done: false, active: false },
    { label: t("upload.step_metrics"), done: false, active: false },
    { label: t("upload.step_ai"),      done: false, active: false },
    { label: t("upload.step_save"),    done: false, active: false },
  ];

  const [processingSteps, setProcessingSteps] = useState<ProcessingStep[]>(makeProcessingSteps);

  // Tick the elapsed-time counter while a run is in flight.
  // This replaces a 6-second carousel that rotated "Читаю транзакции → Считаю
  // показатели → AI изучает динамику → Формирую отчёт" on a timer, completely
  // decoupled from the request: after ~24s it claimed the report was being
  // written while the AI call had barely started. The headline now shows the
  // step that is actually running (see activeLabel below).
  useEffect(() => {
    if (step !== 2 || error) return;
    const timer = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, [step, error]);

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) {
      setFile(accepted[0]);
      setError(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    // The backend decides the real format from the file's content signature,
    // so this list only needs to let the file through the picker. 1C and bank
    // clients mislabel exports constantly, hence octet-stream and text/html.
    accept: {
      "text/csv": [".csv"],
      "text/plain": [".csv", ".txt"],
      "application/vnd.ms-excel": [".xls"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "text/html": [".xls"],
      "application/pdf": [".pdf"],
      "application/octet-stream": [".csv", ".xls", ".xlsx", ".pdf"],
    },
    maxFiles: 1,
  });

  const markStep = (idx: number, done: boolean, active: boolean) => {
    setProcessingSteps((prev) =>
      prev.map((s, i) => i === idx ? { ...s, done, active } : s)
    );
  };

  const runAnalysis = async () => {
    if (!file) return;
    setStep(2);
    setError(null);
    setOutOfReports(false);
    setElapsed(0);
    setAiStartedAt(null);
    setComputed(null);
    setProcessingSteps(makeProcessingSteps());

    try {
      markStep(0, false, true);
      const parseResult = await api.uploadCSV(file);
      setParseResult(parseResult);
      markStep(0, true, false);

      markStep(1, false, true);
      const metrics = await api.analyzeTransactions(parseResult.transactions, businessInfo.closing_balance);
      setMetrics(metrics);
      setComputed(metrics);
      markStep(1, true, false);

      markStep(2, false, true);
      setAiStartedAt(Date.now());
      const report = await api.generateAIReport(metrics, businessInfo);
      setReport(report);
      markStep(2, true, false);
      loadCredits();

      markStep(3, false, true);
      if (user) {
        await saveToSupabase(user.id);
      }
      markStep(3, true, false);

      navigate("/report");
    } catch (err: unknown) {
      // The response interceptor already turned this into an ApiError carrying
      // the backend's own detail, so digging for `err.response` here found
      // nothing and every failure collapsed into the generic default — which
      // hid the specific ones the user can act on ("daily limit reached",
      // "confirm your email").
      if (err instanceof ApiError && err.status === 402) {
        // The server's own sentence, already in the interface language and
        // already "free" or "package" — the same text as the banner.
        setOutOfReports(true);
        setError(parseApiError(err));
      } else {
        setError(parseApiError(err) || t("upload.error_default"));
      }
      // A failed analysis is refunded on the server; show the real balance.
      loadCredits();
      // Stay on step 2 — let user retry or go back
    }
  };

  const handleRetry = () => {
    setError(null);
    runAnalysis();
  };

  const handleBackToSettings = () => {
    setError(null);
    setStep(1);
    setProcessingSteps(makeProcessingSteps());
  };

  const aiElapsed = aiStartedAt !== null && processingSteps[2].active
    ? Math.floor((Date.now() - aiStartedAt) / 1000)
    : null;
  // Headline text = the step actually in flight, derived from real state.
  const activeLabel = processingSteps.find((s) => s.active)?.label ?? processingSteps[0].label;

  return (
    <div className="p-4 sm:p-6 md:p-8 max-w-2xl mx-auto">
      {/* No standing "server may be waking up" banner: a sleeping server is
          handled where it happens, by the wake screen (api/serverWake.ts). */}

      {/* Step indicator */}
      <div className="flex items-center gap-2 sm:gap-3 mb-8 md:mb-10">
        {STEPS.map((label, i) => (
          <div key={i} className="flex items-center gap-3">
            <div className={`flex items-center gap-2 text-sm font-medium ${
              i === step ? "text-brand-blue" : i < step ? "text-fg-subtle" : "text-brand-muted"
            }`}>
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                i === step ? "bg-brand-blue text-white" :
                i < step ? "bg-line/40 text-fg-subtle" :
                "bg-ground text-brand-muted"
              }`}>
                {i < step ? <CheckCircle size={14} /> : i + 1}
              </div>
              <span className={i === step ? "" : "hidden sm:inline"}>{label}</span>
            </div>
            {i < STEPS.length - 1 && <ChevronRight size={14} className="text-brand-border" />}
          </div>
        ))}
      </div>

      {/* Step 0: Drop file */}
      {step === 0 && (
        <div>
          <h1 className="text-2xl font-bold text-brand-dark mb-2">{t("upload.title_upload")}</h1>
          <p className="text-brand-muted text-sm mb-6">{t("upload.subtitle_upload")}</p>

          <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-2xl min-h-[200px] sm:min-h-[280px] flex flex-col items-center justify-center p-6 sm:p-8 cursor-pointer transition-colors ${
              isDragActive
                ? "border-brand-blue bg-line/40"
                : file
                ? "border-accent bg-accent/10"
                : "border-brand-border bg-transparent hover:border-brand-blue hover:bg-ground"
            }`}
          >
            <input {...getInputProps()} />
            {file ? (
              <div className="flex flex-col items-center gap-3 text-center">
                <FileSpreadsheet size={44} className="text-fg-subtle" />
                <p className="font-semibold text-brand-dark">{file.name}</p>
                <p className="text-sm text-brand-muted">{(file.size / 1024).toFixed(1)} KB</p>
                <p className="text-xs text-fg-subtle font-medium">{t("upload.file_selected")}</p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3 text-center">
                <Upload size={44} className="text-brand-muted" />
                <p className="font-semibold text-brand-dark text-lg">
                  {isDragActive ? t("upload.drag_active") : t("upload.drag_hint")}
                </p>
                <p className="text-sm text-brand-muted">{t("upload.file_support")}</p>
              </div>
            )}
          </div>

          <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-xs text-brand-muted space-y-1">
              <p>{t("upload.columns_hint")} <strong>{t("upload.columns_bold")}</strong></p>
              <p>{t("upload.separators_hint")}</p>
            </div>
            <button
              type="button"
              onClick={downloadSampleCSV}
              className="flex items-center gap-1.5 min-h-11 text-xs text-brand-blue hover:underline shrink-0 sm:ml-4"
            >
              <Download size={13} />
              {t("upload.download_sample")}
            </button>
          </div>

          {/* For someone who has never exported a statement. */}
          <div className="mt-4">
            <ExportHelp onDownloadSample={downloadSampleCSV} />
          </div>

          <Button className="w-full mt-6" size="lg" disabled={!file} onClick={() => setStep(1)}>
            {t("common.next")}
          </Button>
        </div>
      )}

      {/* Step 1: Business info */}
      {step === 1 && (
        <div>
          <h1 className="text-2xl font-bold text-brand-dark mb-2">{t("upload.title_settings")}</h1>
          <p className="text-brand-muted text-sm mb-6">{t("upload.subtitle_settings")}</p>

          <Card>
            <CardContent className="pt-6 space-y-5">
              <div className="space-y-1.5">
                <Label>{t("upload.business_name_label")}</Label>
                <Input
                  placeholder={t("upload.business_name_placeholder")}
                  value={businessInfo.name}
                  onChange={(e) => setBusinessInfo({ name: e.target.value })}
                />
              </div>

              <div className="space-y-1.5">
                <Label>{t("upload.business_type_label")}</Label>
                <div className="flex flex-wrap gap-2">
                  {BUSINESS_TYPES.map((bt) => (
                    <button
                      key={bt}
                      type="button"
                      onClick={() => setBusinessInfo({ type: bt })}
                      className={`px-3 py-1.5 max-md:min-h-11 rounded-full text-xs font-medium border transition-colors duration-200 ease-out active:translate-y-px ${
                        businessInfo.type === bt
                          ? "bg-brand-blue text-white border-brand-blue"
                          : "bg-transparent text-brand-muted border-brand-border hover:border-brand-blue"
                      }`}
                    >
                      {bt}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-1.5">
                <Label>{t("upload.period_label")}</Label>
                <Input
                  placeholder={t("upload.period_placeholder")}
                  value={businessInfo.period}
                  onChange={(e) => setBusinessInfo({ period: e.target.value })}
                />
              </div>

              <div className="space-y-1.5">
                <Label>{t("upload.currency_label")}</Label>
                <div className="flex flex-wrap gap-2">
                  {["UZS", "USD", "EUR", "RUB", "KZT"].map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setBusinessInfo({ currency: c })}
                      className={`px-4 py-1.5 max-md:min-h-11 rounded-full text-xs font-bold border transition-colors duration-200 ease-out active:translate-y-px ${
                        businessInfo.currency === c
                          ? "bg-brand-blue text-white border-brand-blue"
                          : "bg-transparent text-brand-muted border-brand-border hover:border-brand-blue"
                      }`}
                    >
                      {c}
                    </button>
                  ))}
                </div>
              </div>

              {/* The only thing that turns the cash forecast into a balance
                  forecast. Optional: without it the report shows the trend of
                  weekly net flow and says why there is no date or amount. */}
              <div className="space-y-1.5">
                <Label htmlFor="closing-balance">
                  {t("cash.balance_label")} ({businessInfo.currency}) — {t("common.optional")}
                </Label>
                <Input
                  id="closing-balance"
                  inputMode="decimal"
                  className="mono-num"
                  placeholder={t("cash.balance_placeholder")}
                  value={balanceText}
                  onChange={(e) => {
                    setBalanceText(e.target.value);
                    setBusinessInfo({ closing_balance: parseAmount(e.target.value) });
                  }}
                />
                <p className={`text-xs ${balanceInvalid ? "text-danger" : "text-brand-muted"}`}>
                  {balanceInvalid ? t("cash.balance_invalid") : t("cash.balance_hint")}
                </p>
              </div>
            </CardContent>
          </Card>

          {/* What this run costs, said before it starts — an empty balance
              must not first appear as an error 40 seconds into an analysis. */}
          {credits && (
            <p className="mt-5 text-xs text-brand-muted">
              {credits.unlimited ? (
                t("credits.unlimited")
              ) : isOutOfReports(credits) ? (
                <span className="text-sev-medium-fg">{t(exhaustedKey(credits))}</span>
              ) : (
                t("credits.will_spend", { count: credits.balance ?? 0 })
              )}
            </p>
          )}

          <div className="flex flex-col-reverse sm:flex-row gap-3 mt-4">
            <Button variant="outline" className="flex-1" onClick={() => setStep(0)}>{t("common.back")}</Button>
            <Button className="flex-1" size="lg" onClick={runAnalysis} disabled={isOutOfReports(credits) || balanceInvalid}>
              {t("upload.btn_analyze")}
            </Button>
          </div>
        </div>
      )}

      {/* Step 2: Processing */}
      {step === 2 && (
        <div className="text-center">
          {!error ? (
            <>
              <div className="w-16 h-16 rounded-2xl bg-line/40 flex items-center justify-center mx-auto mb-4">
                <Loader2 size={28} className="text-brand-blue animate-spin" />
              </div>
              <h1 className="text-2xl font-bold text-brand-dark mb-1">{t("upload.title_processing")}</h1>
              <p className="text-brand-blue text-sm font-medium mb-6">{activeLabel}</p>
            </>
          ) : (
            <>
              <div className="w-16 h-16 rounded-2xl bg-sev-high/15 flex items-center justify-center mx-auto mb-4">
                <AlertCircle size={28} className="text-danger" />
              </div>
              <h1 className="text-2xl font-bold text-brand-dark mb-1">{t("upload.title_processing")}</h1>
              <p className="text-sm text-brand-muted mb-6">&nbsp;</p>
            </>
          )}

          <div className="text-left">
            <AnalysisWait
              steps={processingSteps}
              elapsed={elapsed}
              aiElapsed={aiElapsed}
              metrics={computed}
              currency={businessInfo.currency}
              failed={!!error}
            />
          </div>

          {error && (
            <div className="mt-5 space-y-3">
              <div className="flex items-start gap-2 p-4 bg-sev-high/15 rounded-xl border border-sev-high/40 text-left">
                <AlertCircle size={15} className="text-danger mt-0.5 shrink-0" />
                <p className="text-sm text-danger">{error}</p>
              </div>
              <div className="flex flex-col-reverse sm:flex-row gap-3">
                <Button variant="outline" className="flex-1" onClick={handleBackToSettings}>
                  {t("upload.back_to_settings")}
                </Button>
                {/* Out of reports: retrying cannot help, so it is not offered. */}
                {!outOfReports && (
                  <Button className="flex-1" onClick={handleRetry}>
                    {t("upload.retry_btn")}
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
