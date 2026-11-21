import { useEffect, useRef, useState } from "react";
import { X, Trash2, Send, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/api/endpoints";
import { useExitAnimation } from "@/lib/motion";
import type { AIReport, BusinessInfo, ChatMessage, FinancialMetrics } from "@/types";

const SUGGESTIONS = [
  "Где я теряю больше всего денег?",
  "Есть ли риск кассового разрыва?",
  "Какую статью расходов сократить первой?",
  "Каков прогноз прибыли на следующий месяц?",
];

const CLOSE_MS = 180;

interface Props {
  open: boolean;
  onClose: () => void;
  metrics: FinancialMetrics;
  report: AIReport | null;
  businessInfo: BusinessInfo;
}

function Avatar() {
  return (
    <div className="w-7 h-7 rounded-xs border border-accent/50 flex items-center justify-center shrink-0">
      <Bot size={14} className="text-accent-fg" />
    </div>
  );
}

/** Three dots fading in sequence — opacity only, no bounce. */
function TypingIndicator() {
  return (
    <div className="flex items-end gap-2 mb-3 anim-fade-up">
      <Avatar />
      <div className="bg-ground border border-brand-border rounded-xs px-4 py-3">
        <div className="flex gap-1.5 items-center h-4">
          <span className="w-1.5 h-1.5 rounded-full bg-brand-muted anim-dot" />
          <span className="w-1.5 h-1.5 rounded-full bg-brand-muted anim-dot [animation-delay:200ms]" />
          <span className="w-1.5 h-1.5 rounded-full bg-brand-muted anim-dot [animation-delay:400ms]" />
        </div>
      </div>
    </div>
  );
}

export function AIChatPanel({ open, onClose, metrics, report, businessInfo }: Props) {
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Held mounted while the slide-out plays. Shared with the modal, dropdown
  // and welcome card — they all had the same three lines of timer.
  const { mounted, closing } = useExitAnimation(open, CLOSE_MS);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!open) return;
    const id = setTimeout(() => textareaRef.current?.focus(), 100);
    return () => clearTimeout(id);
  }, [open]);

  useEffect(() => {
    // Scroll the message column itself. scrollIntoView() walks up to every
    // scrollable ancestor, and this panel is `fixed` over a page that has its
    // own scroll — the dashboard behind it used to jump along with the chat.
    const el = scrollRef.current;
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollTo({ top: el.scrollHeight, behavior: reduce ? "auto" : "smooth" });
  }, [history, loading]);

  const send = async (msg: string) => {
    const text = msg.trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = { role: "user", content: text };
    const nextHistory = [...history, userMsg];
    setHistory(nextHistory);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const answer = await api.sendChatMessage(
        text,
        history,
        metrics,
        report,
        businessInfo
      );
      setHistory([...nextHistory, { role: "assistant", content: answer }]);
    } catch {
      setError("Ошибка соединения с сервером. Попробуйте ещё раз.");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  };

  if (!mounted) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-ground/50 z-40 md:hidden anim-fade-in"
        onClick={onClose}
      />

      {/* Panel. bg-header is a SOLID fill, deliberately not a token with alpha:
          this floats over the dashboard, so anything translucent lets the page
          behind it read through the conversation. In-flow cards stay
          fill-less — that rule belongs to the page, not to overlays. */}
      <div
        className={`fixed right-0 top-0 h-full w-full md:w-[420px] bg-header border-l border-brand-border z-50 flex flex-col ${
          closing ? "anim-panel-out" : "anim-panel-in"
        }`}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-brand-border shrink-0">
          <Avatar />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-brand-dark">AI-CFO</p>
            <p className="text-xs text-brand-muted truncate">
              {businessInfo.name || "Финансовый советник"}
            </p>
          </div>
          <button
            onClick={() => { setHistory([]); setError(null); }}
            className="p-1.5 rounded-xs text-brand-muted hover:text-brand-dark transition-colors duration-200 ease-out"
            title="Очистить чат"
          >
            <Trash2 size={15} />
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded-xs text-brand-muted hover:text-brand-dark transition-colors duration-200 ease-out"
            title="Закрыть"
          >
            <X size={15} />
          </button>
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-1">
          {history.length === 0 && !loading && (
            <div className="flex flex-col items-start gap-4 anim-fade-in">
              {/* Greeting bubble */}
              <div className="flex items-end gap-2">
                <Avatar />
                <div className="bg-ground border border-brand-border rounded-xs px-4 py-3 max-w-[85%]">
                  <p className="text-sm text-brand-dark leading-relaxed">
                    Привет! Я AI-CFO для{" "}
                    <span className="font-semibold">
                      {businessInfo.name || "вашего бизнеса"}
                    </span>
                    . Задайте вопрос по финансовым данным — я отвечу на основе вашего отчёта.
                  </p>
                </div>
              </div>

              {/* Suggestion chips */}
              <div className="flex flex-col gap-2 w-full pl-9">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="text-left text-xs px-3 py-2 rounded-xs border border-brand-border text-brand-muted hover:text-accent-fg hover:border-accent-fg transition-colors duration-200 ease-out leading-snug"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {history.map((m, i) =>
            m.role === "user" ? (
              // The animation runs once, on mount: React keeps these nodes
              // across re-renders, so earlier messages do not re-play.
              <div key={i} className="flex justify-end mb-3 anim-fade-up">
                <div className="border border-accent/60 bg-accent/12 rounded-xs px-4 py-2.5 max-w-[85%]">
                  <p className="text-sm text-brand-dark leading-relaxed whitespace-pre-wrap">{m.content}</p>
                </div>
              </div>
            ) : (
              <div key={i} className="flex items-end gap-2 mb-3 anim-fade-up">
                <Avatar />
                <div className="bg-ground border border-brand-border rounded-xs px-4 py-3 max-w-[85%]">
                  <p className="text-sm text-brand-dark leading-relaxed whitespace-pre-wrap">{m.content}</p>
                </div>
              </div>
            )
          )}

          {loading && <TypingIndicator />}

          {error && (
            <div className="text-xs text-sev-high-fg bg-sev-high/10 border border-sev-high/60 rounded-xs px-3 py-2 mb-2 anim-fade-in">
              {error}
            </div>
          )}
        </div>

        {/* Input */}
        <div className="px-4 py-3 border-t border-brand-border shrink-0">
          <div className="flex items-end gap-2">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Спросите о финансах бизнеса…"
              rows={1}
              className="flex-1 resize-none rounded-xs border border-brand-border bg-ground px-3 py-2.5 text-sm text-brand-dark placeholder:text-fg-subtle focus:outline-none focus:border-accent-fg transition-colors duration-200 ease-out max-h-32 overflow-y-auto"
              style={{ minHeight: "42px" }}
              disabled={loading}
            />
            <Button
              size="icon"
              onClick={() => send(input)}
              disabled={!input.trim() || loading}
              className="shrink-0 h-[42px] w-[42px]"
            >
              <Send size={16} />
            </Button>
          </div>
          <p className="text-[10px] text-brand-muted mt-1.5 text-center">
            Enter — отправить · Shift+Enter — новая строка
          </p>
        </div>
      </div>
    </>
  );
}
