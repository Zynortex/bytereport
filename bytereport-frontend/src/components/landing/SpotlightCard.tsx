import { useRef } from "react";
import { cn } from "@/lib/utils";

/**
 * A card whose 1px frame lights up under the cursor.
 *
 * At rest: the line colour. On hover: the frame turns accent, and a soft
 * spotlight follows the pointer ALONG THE FRAME ONLY — the layer is masked to
 * a 1px ring, so no fill ever reaches the card's surface. Colours and sizes
 * are the --fx-* tokens (design-tokens.json → effects).
 */
export function SpotlightCard({ children, className }: { children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);

  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--x", `${e.clientX - r.left}px`);
    el.style.setProperty("--y", `${e.clientY - r.top}px`);
  };

  return (
    <div
      ref={ref}
      onPointerMove={onMove}
      className={cn(
        "group relative rounded-xs border border-brand-border bg-surface transition-colors duration-[var(--dur-hover)] ease-out hover:border-accent",
        className
      )}
    >
      <div
        aria-hidden="true"
        className="spotlight-frame pointer-events-none absolute -inset-px rounded-[inherit] opacity-0 transition-opacity duration-[var(--dur-hover)] ease-out group-hover:opacity-100"
      />
      {children}
    </div>
  );
}
