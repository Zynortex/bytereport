import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { useExitAnimation } from "@/lib/motion";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  title: string;
  text: string;
  confirmLabel: string;
  cancelLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * A yes/no question before something irreversible. The same overlay language
 * as every other modal: a fading backdrop, a surface that settles from 0.97.
 * Escape and the backdrop both mean "no".
 */
export function ConfirmDialog({ open, title, text, confirmLabel, cancelLabel, busy, onConfirm, onCancel }: Props) {
  const { mounted, closing } = useExitAnimation(open, 150);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!mounted) return null;
  return (
    <div
      className={cn("fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4", closing ? "anim-fade-out" : "anim-fade-in")}
      onClick={onCancel}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-text"
        className={cn("bg-header border border-brand-border rounded-xs p-6 max-w-sm w-full", closing ? "anim-pop-out" : "anim-pop-in")}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="confirm-title" className="text-base font-bold text-brand-dark mb-2">{title}</h3>
        <p id="confirm-text" className="text-sm text-brand-muted leading-relaxed mb-6">{text}</p>
        <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
          <Button variant="outline" onClick={onCancel} autoFocus>{cancelLabel}</Button>
          <Button variant="danger" onClick={onConfirm} loading={busy}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  );
}
