import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  AlertCircle, CheckCircle, Download, FileSpreadsheet, ImagePlus, Loader2, Mic,
  Square,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DraftTable } from "@/components/voice/DraftTable";
import { api } from "@/api/endpoints";
import { isAuthError, parseApiError } from "@/api/client";
import { SILENCE_PEAK, useRecorder } from "@/lib/useRecorder";
import { formatCurrency } from "@/lib/utils";
import type { DraftTransaction } from "@/types";

const CURRENCIES = ["UZS", "RUB", "USD", "EUR", "KZT"];

/** input -> preview -> done. There is no path that skips `preview`. */
type Stage = "input" | "preview" | "done";

/**
 * Which input produced the current draft. Only the preview's left column
 * differs: a photo cannot be "edited and re-parsed" the way a transcript can,
 * so that column offers a re-shoot instead.
 */
type SourceKind = "text" | "photo";

// Matches photo_parser.MAX_IMAGE_BYTES. Checked here as well so an obvious
// mistake costs a message rather than a 10 MB upload.
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

export default function VoiceNote() {
  const { t, i18n } = useTranslation();
  const recorder = useRecorder();

  const [stage, setStage] = useState<Stage>("input");
  const [text, setText] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [currency, setCurrency] = useState("UZS");

  const [rows, setRows] = useState<DraftTransaction[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [recordsNeeded, setRecordsNeeded] = useState(30);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [sourceKind, setSourceKind] = useState<SourceKind>("text");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [busy, setBusy] = useState<null | "transcribe" | "parse" | "photo" | "excel">(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);

  const showError = (err: unknown) => {
    // Branch on the status, not on the wording: the message is translated and
    // the backend owns its phrasing.
    setSessionExpired(isAuthError(err));
    setError(parseApiError(err));
  };

  const totals = useMemo(() => {
    let income = 0, expense = 0;
    for (const r of rows) {
      if (r.amount == null) continue;
      if (r.direction === "income") income += r.amount;
      else expense += r.amount;
    }
    return { income, expense, net: income - expense };
  }, [rows]);

  // Object URLs hold their blob until revoked. Releasing on replacement and
  // on unmount keeps a session of re-shot photos from pinning every attempt
  // in memory.
  useEffect(() => () => {
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    if (audioUrl) URL.revokeObjectURL(audioUrl);
  }, [photoUrl, audioUrl]);

  // ── Voice ────────────────────────────────────────────────────────────────

  const stopAndTranscribe = async () => {
    // stop() resolves with the recording itself — see useRecorder for why
    // reading it back off state cannot work.
    const { blob: audio, peak } = await recorder.stop();
    if (!audio) {
      setError(t("voice.record_empty"));
      return;
    }
    // Refuse to upload silence. The model does not answer "nothing was said" —
    // it invents a sentence, which would land in the note looking like the
    // user's own words.
    if (peak < SILENCE_PEAK) {
      setError(t("voice.record_silent"));
      return;
    }

    setBusy("transcribe");
    setError(null);
    try {
      const res = await api.transcribeNote(audio, i18n.language || "ru");
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      setAudioUrl(URL.createObjectURL(audio));
      if (!res.text.trim()) {
        setError(t("voice.record_silent"));
        return;
      }
      // Append rather than replace: a user who already typed half the note and
      // then dictated the rest should not lose what they typed.
      setText((prev) => (prev.trim() ? `${prev.trim()} ${res.text}` : res.text));
    } catch (err) {
      showError(err);
    } finally {
      setBusy(null);
    }
  };

  // ── Photo ────────────────────────────────────────────────────────────────

  const pickPhoto = () => fileInputRef.current?.click();

  const onPhotoChosen = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    // Reset the input so choosing the SAME file twice still fires a change —
    // the whole point of "another photo" is often re-taking the same shot.
    e.target.value = "";
    if (!file) return;

    if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) {
      setError(t("voice.photo_not_image"));
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setError(t("voice.photo_too_big"));
      return;
    }

    setBusy("photo");
    setError(null);
    try {
      const res = await api.parsePhoto(file, currency);
      if (photoUrl) URL.revokeObjectURL(photoUrl);
      setPhotoUrl(URL.createObjectURL(file));
      setRows(res.transactions);
      setWarnings(res.warnings);
      setRecordsNeeded(res.records_needed);
      setSourceKind("photo");
      setStage("preview");
    } catch (err) {
      showError(err);
    } finally {
      setBusy(null);
    }
  };

  // ── Parse ────────────────────────────────────────────────────────────────

  const runParse = async () => {
    if (!text.trim()) return;
    setBusy("parse");
    setError(null);
    try {
      const res = await api.parseNote(text, currency);
      setRows(res.transactions);
      setWarnings(res.warnings);
      setRecordsNeeded(res.records_needed);
      setSourceKind("text");
      setStage("preview");
    } catch (err) {
      showError(err);
    } finally {
      setBusy(null);
    }
  };

  // ── Confirm ──────────────────────────────────────────────────────────────

  const downloadExcel = async () => {
    setBusy("excel");
    setError(null);
    try {
      const blob = await api.downloadNoteExcel(rows, businessName, currency);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `bytereport_note.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      setStage("done");
    } catch (err) {
      showError(err);
    } finally {
      setBusy(null);
    }
  };

  const startOver = () => {
    setStage("input");
    setText("");
    setRows([]);
    setWarnings([]);
    setError(null);
    setAudioUrl(null);
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    setPhotoUrl(null);
    setSourceKind("text");
    recorder.reset();
  };

  const recording = recorder.state === "recording";

  // ── Note editor, shared by the input stage and the preview's left column ──
  //
  // A plain function returning JSX, NOT a component declared in the render
  // body. As <NoteEditor /> it was a new component TYPE on every render, so
  // React unmounted and rebuilt the textarea after each keystroke and focus
  // jumped to <body> — the field accepted exactly one character at a time.
  // Calling it inlines the JSX into this component's tree instead.

  const noteEditor = (compact?: boolean) => (
    <>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={t("voice.input_placeholder")}
        rows={compact ? 8 : 5}
        disabled={busy !== null}
        className="w-full resize-y rounded-xs border border-brand-border bg-transparent px-3 py-2.5 text-sm text-brand-dark placeholder:text-fg-subtle transition-[border-color] duration-200 ease-out focus:outline-none focus:border-accent-fg focus:ring-2 focus:ring-accent/30 disabled:opacity-60"
      />

      <div className="flex flex-wrap items-center gap-3 mt-3">
        <Button
          variant={recording ? "danger" : "outline"}
          size="sm"
          onClick={recording ? stopAndTranscribe : recorder.start}
          disabled={busy !== null}
        >
          {recording ? <Square size={13} /> : <Mic size={13} />}
          {recording ? t("voice.record_stop") : t("voice.record_start")}
        </Button>

        {recording && (
          <span className="flex items-center gap-2 text-xs text-sev-high-fg">
            <span className="w-1.5 h-1.5 rounded-full bg-sev-high-fg anim-dot" />
            {t("voice.recording")} · {recorder.seconds}s
          </span>
        )}
        <Button variant="outline" size="sm" onClick={pickPhoto} disabled={busy !== null}>
          <ImagePlus size={13} />
          {t("voice.photo_btn")}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="hidden"
          onChange={onPhotoChosen}
        />

        {busy === "photo" && (
          <span className="flex items-center gap-2 text-xs text-brand-muted">
            <Loader2 size={13} className="animate-spin" />
            {t("voice.photo_reading")}
          </span>
        )}
        {busy === "transcribe" && (
          <span className="flex items-center gap-2 text-xs text-brand-muted">
            <Loader2 size={13} className="animate-spin" />
            {t("voice.transcribing")}
          </span>
        )}
        {!compact && busy === null && (
          <span className="text-xs text-fg-subtle basis-full">{t("voice.photo_hint")}</span>
        )}
        {recorder.state === "denied" && (
          <span className="text-xs text-sev-medium-fg">{t("voice.mic_denied")}</span>
        )}
        {recorder.state === "unsupported" && (
          <span className="text-xs text-sev-medium-fg">{t("voice.mic_unsupported")}</span>
        )}
      </div>

      {/* The recording stays available for comparison, exactly like the text. */}
      {audioUrl && (
        <div className="mt-4">
          <p className="label-caps text-[10px] text-brand-muted mb-1.5">{t("voice.audio_title")}</p>
          <audio src={audioUrl} controls className="w-full h-9" />
        </div>
      )}
    </>
  );

  return (
    <div className="p-4 sm:p-6 md:p-8">
      <h1 className="text-display text-2xl text-brand-dark">{t("voice.title")}</h1>
      <p className="text-brand-muted text-sm mt-1 mb-7 max-w-2xl leading-relaxed">
        {t("voice.subtitle")}
      </p>

      {error && (
        <div className="flex items-start gap-2 mb-6 rounded-xs border border-sev-high/60 bg-sev-high/10 px-4 py-3 anim-fade-in">
          <AlertCircle size={15} className="text-sev-high-fg shrink-0 mt-0.5" />
          <div className="text-sm text-sev-high-fg leading-relaxed">
            <p>{error}</p>
            {/* An expired session is the one error the user cannot fix from
                here, so it gets the action instead of a dead end. Everything
                else stays a message on the form the user is already looking
                at, rather than a navigation away from their work. */}
            {sessionExpired && (
              <Link
                to="/auth"
                className="mt-1 inline-block underline underline-offset-4 hover:text-brand-dark transition-colors duration-200 ease-out"
              >
                {t("common.sign_in_again")}
              </Link>
            )}
          </div>
        </div>
      )}

      {/* ── Stage 1: the note ────────────────────────────────────────────── */}
      {stage === "input" && (
        <Card className="anim-fade-up max-w-3xl">
          <CardContent className="p-4 sm:p-6 space-y-5">
            <div>
              <Label className="mb-1.5 block">{t("voice.input_label")}</Label>
              {noteEditor()}
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <Label className="mb-1.5 block">{t("voice.business_name_label")}</Label>
                <Input
                  value={businessName}
                  onChange={(e) => setBusinessName(e.target.value)}
                  placeholder={t("voice.business_name_placeholder")}
                />
              </div>
              <div>
                <Label className="mb-1.5 block">{t("voice.currency_label")}</Label>
                <div className="flex gap-2">
                  {CURRENCIES.map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => setCurrency(c)}
                      className={`flex-1 py-2 max-md:min-h-11 rounded-xs border text-xs label-caps transition-colors duration-200 ease-out active:translate-y-px ${
                        currency === c
                          ? "border-accent text-accent-fg bg-accent/12"
                          : "border-brand-border text-brand-muted hover:text-brand-dark"
                      }`}
                    >
                      {c}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <Button
              size="lg"
              onClick={runParse}
              disabled={!text.trim() || busy !== null}
              loading={busy === "parse"}
            >
              {busy === "parse" ? t("voice.parsing") : t("voice.parse_btn")}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* ── Stage 2: mandatory preview, source alongside ─────────────────── */}
      {stage === "preview" && (
        <div className="grid lg:grid-cols-12 gap-6 anim-fade-up">
          {/* The source stays visible for comparison in every mode. What
              differs is the correction it offers: a transcript can be edited
              and re-parsed, a photograph can only be re-taken. */}
          <Card className="lg:col-span-3 h-fit">
            <CardContent className="p-5">
              <p className="label-caps text-[11px] text-brand-muted">
                {sourceKind === "photo" ? t("voice.photo_title") : t("voice.source_title")}
              </p>
              <span className="block w-8 h-px bg-accent mt-2.5 mb-4" aria-hidden="true" />

              {sourceKind === "photo" ? (
                <>
                  {photoUrl && (
                    <img
                      src={photoUrl}
                      alt={t("voice.photo_title")}
                      className="w-full rounded-xs border border-brand-border"
                    />
                  )}
                  <p className="text-xs text-brand-muted leading-relaxed mt-4">
                    {t("voice.photo_source_hint")}
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-3 w-full"
                    onClick={pickPhoto}
                    disabled={busy !== null}
                    loading={busy === "photo"}
                  >
                    <ImagePlus size={13} />
                    {t("voice.photo_replace")}
                  </Button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    onChange={onPhotoChosen}
                  />
                </>
              ) : (
                <>
                  {noteEditor(true)}
                  <p className="text-xs text-brand-muted leading-relaxed mt-4">{t("voice.source_hint")}</p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-3 w-full"
                    onClick={runParse}
                    disabled={!text.trim() || busy !== null}
                    loading={busy === "parse"}
                  >
                    {t("voice.reparse_btn")}
                  </Button>
                </>
              )}
            </CardContent>
          </Card>

          {/* Level (b): edit the values directly, no re-parse. */}
          <div className="lg:col-span-9 space-y-4 min-w-0">
            <div>
              <p className="label-caps text-[11px] text-brand-muted">{t("voice.preview_title")}</p>
              <span className="block w-8 h-px bg-accent mt-2.5 mb-3" aria-hidden="true" />
              <p className="text-xs text-brand-muted leading-relaxed max-w-xl">{t("voice.preview_hint")}</p>
            </div>

            {warnings.length > 0 && (
              <ul className="space-y-1">
                {warnings.map((w, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs text-sev-medium-fg leading-relaxed">
                    <AlertCircle size={13} className="shrink-0 mt-0.5" />
                    {w}
                  </li>
                ))}
              </ul>
            )}

            {rows.length === 0 ? (
              <p className="text-sm text-brand-muted border border-brand-border rounded-xs px-4 py-6">
                {t("voice.empty_preview")}
              </p>
            ) : (
              <>
                <DraftTable rows={rows} onChange={setRows} currency={currency} disabled={busy !== null} />

                <p className="text-xs text-brand-muted mono-num">
                  {t("voice.totals", {
                    income: formatCurrency(totals.income, currency),
                    expense: formatCurrency(totals.expense, currency),
                    net: formatCurrency(totals.net, currency),
                  })}
                </p>

                <Button
                  size="lg"
                  className="w-full sm:w-auto"
                  onClick={downloadExcel}
                  disabled={busy !== null}
                  loading={busy === "excel"}
                >
                  <FileSpreadsheet size={15} />
                  {busy === "excel" ? t("voice.generating") : t("voice.confirm_btn")}
                </Button>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Stage 3: the file, and an honest word about what it is not ───── */}
      {stage === "done" && (
        <Card className="anim-fade-up max-w-2xl">
          <CardContent className="p-5 sm:p-7">
            <div className="flex items-center gap-2.5">
              <CheckCircle size={17} className="text-success" />
              <p className="text-base font-semibold text-brand-dark">{t("voice.done_title")}</p>
            </div>
            <span className="block w-8 h-px bg-accent mt-4 mb-5" aria-hidden="true" />
            <p className="text-sm text-brand-muted leading-relaxed">
              {t("voice.done_text", { n: recordsNeeded })}
            </p>
            <div className="flex flex-wrap gap-3 mt-6">
              <Button variant="outline" onClick={downloadExcel} loading={busy === "excel"}>
                <Download size={14} />
                {t("voice.download_again")}
              </Button>
              <Button variant="secondary" onClick={startOver}>{t("voice.start_over")}</Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
