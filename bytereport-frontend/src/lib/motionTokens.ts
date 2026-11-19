/**
 * Motion and effect tokens, from repo-root design-tokens.json — the only
 * place a duration, the easing curve or an effect colour is written down.
 * Components import these; nothing hardcodes a millisecond.
 */
import tokens from "../../../design-tokens.json";

const m = tokens.motion;

/** The house curve: ease-out, no overshoot. */
export const EASE = m.ease as [number, number, number, number];

const s = (ms: number) => ms / 1000;

/** Seconds, as Motion's `transition.duration` wants them. */
export const DUR = {
  hover: s(m.hover_ms),
  press: s(m.press_ms),
  reveal: s(m.reveal_ms),
  stagger: s(m.stagger_ms),
  draw: s(m.draw_ms),
  count: s(m.count_ms),
} as const;

export const MS = {
  count: m.count_ms,
  draw: m.draw_ms,
  heroCycle: m.hero_cycle_ms,
} as const;

export const REVEAL_OFFSET = m.reveal_offset_px;
export const PRESS_SCALE = m.press_scale;
export const EFFECTS = tokens.effects;
