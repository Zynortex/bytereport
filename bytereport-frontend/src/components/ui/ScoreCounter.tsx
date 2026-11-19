import { useEffect, useRef, useState } from "react";

interface Props {
  value: number;
  /** Run the count-up when this flips to true. */
  active?: boolean;
  /** Must match the PulseLine duration alongside it so both land together. */
  duration?: number;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Counts 0 → `value` on requestAnimationFrame. Pair it with a PulseLine on the
 * same `active` flag and the same `duration` so the number and the trace finish
 * on the same frame.
 */
export function ScoreCounter({ value, active = true, duration = 1400, className, style }: Props) {
  const [display, setDisplay] = useState(0);
  const frameRef = useRef(0);

  useEffect(() => {
    if (!active) {
      setDisplay(0);
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setDisplay(value);
      return;
    }

    const start = performance.now();
    const tick = (now: number) => {
      // Clamped for the same reason as PulseLine: an early rAF timestamp would
      // otherwise make the counter flash a negative number on the first frame.
      const t = Math.min(Math.max((now - start) / duration, 0), 1);
      const eased = 1 - (1 - t) ** 3;
      setDisplay(Math.round(eased * value));
      if (t < 1) frameRef.current = requestAnimationFrame(tick);
    };
    frameRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameRef.current);
  }, [active, value, duration]);

  return (
    <span className={className} style={style}>
      {display}
    </span>
  );
}
