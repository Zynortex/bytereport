import { useEffect, useRef, useState } from "react";
import { EASE } from "@/lib/motionTokens";
import { useReducedMotion } from "@/lib/motion";

/**
 * The house curve as a function of time, for things Motion does not drive
 * (a number rendered as text). Standard cubic-bezier with P0=(0,0), P3=(1,1):
 * solve x(s)=t for s by Newton's method, return y(s).
 */
export function bezier([x1, y1, x2, y2]: readonly [number, number, number, number]) {
  const ax = 3 * x1 - 3 * x2 + 1, bx = 3 * x2 - 6 * x1, cx = 3 * x1;
  const ay = 3 * y1 - 3 * y2 + 1, by = 3 * y2 - 6 * y1, cy = 3 * y1;
  const x = (s: number) => ((ax * s + bx) * s + cx) * s;
  const dx = (s: number) => (3 * ax * s + 2 * bx) * s + cx;
  const y = (s: number) => ((ay * s + by) * s + cy) * s;
  return (t: number) => {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    let s = t;
    for (let i = 0; i < 6; i++) {
      const d = dx(s);
      if (Math.abs(d) < 1e-6) break;
      s -= (x(s) - t) / d;
    }
    return y(Math.min(Math.max(s, 0), 1));
  };
}

const ease = bezier(EASE);

/**
 * 0 → target over `durationMs` once `active` turns true, on the house curve.
 * Under reduced motion it is the target from the start: a count-up is motion.
 */
export function useCountUp(target: number, active: boolean, durationMs: number): number {
  const reduced = useReducedMotion();
  const [value, setValue] = useState(reduced ? target : 0);
  const frame = useRef(0);

  useEffect(() => {
    if (reduced) { setValue(target); return; }
    if (!active) return;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(Math.max((now - start) / durationMs, 0), 1);
      setValue(target * ease(t));
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [active, target, durationMs, reduced]);

  return value;
}
