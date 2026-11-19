/**
 * Behind the hero: a very dark accent glow and a fine grid that fades out
 * toward the edges. Static — no drift, nothing to repaint. Both colours are
 * tokens (--fx-glow: #6B5482 at 11%, --fx-grid: primary text at 4%); the
 * masks are alpha only and paint nothing themselves.
 */
export function HeroBackdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            "linear-gradient(var(--fx-grid) 1px, transparent 1px), linear-gradient(90deg, var(--fx-grid) 1px, transparent 1px)",
          backgroundSize: "var(--fx-grid-size) var(--fx-grid-size)",
          maskImage: "radial-gradient(ellipse 75% 65% at 50% 40%, black 25%, transparent 80%)",
          WebkitMaskImage: "radial-gradient(ellipse 75% 65% at 50% 40%, black 25%, transparent 80%)",
        }}
      />
      <div
        className="absolute inset-0"
        style={{ background: "radial-gradient(ellipse 50% 55% at 72% 42%, var(--fx-glow), transparent 72%)" }}
      />
    </div>
  );
}
