/**
 * Behind the hero: two faint glows, the cyan accent and the chart blue (as in
 * the ByteForge hero), and a fine grid that fades out toward the edges.
 * Static — no drift, nothing to repaint. Every colour is a token (--fx-glow,
 * --fx-glow-2: 11% opacity; --fx-grid: primary text at 4%); the masks are
 * alpha only and paint nothing themselves.
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
      <div
        className="absolute inset-0"
        style={{ background: "radial-gradient(ellipse 45% 50% at 18% 12%, var(--fx-glow-2), transparent 70%)" }}
      />
    </div>
  );
}
