import { cn } from "@/lib/utils";

// Risk is the one place a semantic colour is justified. Muted, outlined, and
// drawn from the shared tokens so the PDF badges match exactly.
const VARIANTS: Record<string, string> = {
  high:   "text-sev-high border-sev-high/60",
  medium: "text-sev-medium border-sev-medium/60",
  low:    "text-sev-low border-sev-low/60",
};

interface Props {
  severity: string;
  className?: string;
}

export function SeverityBadge({ severity, className }: Props) {
  const key = severity.toLowerCase();
  return (
    <span
      className={cn(
        "inline-flex items-center border bg-transparent px-2 py-0.5 rounded-xs label-caps text-[10px] shrink-0",
        VARIANTS[key] ?? "text-brand-muted border-brand-border",
        className,
      )}
    >
      {severity.toUpperCase()}
    </span>
  );
}
