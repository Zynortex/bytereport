import { useEffect, useState } from "react";

/**
 * Single source for "may this surface animate?".
 *
 * CSS animations opt out through the media query in index.css, but recharts
 * animates in JS and cannot see it — it needs the answer as a boolean prop.
 * Both paths read the same OS setting, so they can't disagree.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return reduced;
}

/**
 * Chart entrance timings. Short and ease-out: the bars grow into place and
 * stop. Series are offset so the eye reads revenue, then expenses, then
 * profit, rather than three shapes arriving on the same frame.
 */
export const CHART_ANIM_MS = 620;
export const CHART_STAGGER_MS = 110;

/**
 * Keeps a surface mounted long enough to play its exit animation.
 *
 * Conditional rendering (`{open && <Panel/>}`) removes the node on the same
 * frame the flag flips, so a closing animation never gets to run. This holds
 * the node for `exitMs` and reports `closing` so the caller can swap the
 * animation class.
 *
 * Returns immediately (no exit hold) under reduced motion — there is nothing
 * to wait for, and delaying the unmount would just make the UI feel laggy.
 */
export function useExitAnimation(open: boolean, exitMs: number) {
  const reduced = useReducedMotion();
  const [mounted, setMounted] = useState(open);
  const [closing, setClosing] = useState(false);

  useEffect(() => {
    if (open) {
      setClosing(false);
      setMounted(true);
      return;
    }
    if (!mounted) return;
    if (reduced) { setMounted(false); return; }
    setClosing(true);
    const id = setTimeout(() => { setMounted(false); setClosing(false); }, exitMs);
    return () => clearTimeout(id);
  // `mounted` is deliberately not a dependency: re-running this effect when it
  // changes would restart the timer it just set.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, reduced, exitMs]);

  return { mounted, closing };
}
