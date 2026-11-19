import { m, type Variants } from "motion/react";
import { DUR, EASE, REVEAL_OFFSET } from "@/lib/motionTokens";

const group: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: DUR.stagger } },
};

const item: Variants = {
  hidden: { opacity: 0, y: REVEAL_OFFSET },
  show: { opacity: 1, y: 0, transition: { duration: DUR.reveal, ease: EASE } },
};

interface Props {
  children: React.ReactNode;
  className?: string;
  /** Share of the block that must be on screen before it plays. */
  amount?: number;
}

/**
 * A section that arrives once, the first time it scrolls into view: its
 * RevealItem children fade up 14px one after another (70 ms apart). Under
 * reduced motion MotionConfig drops the travel and only the fade remains.
 * Opacity and transform only — nothing here can shift the layout.
 */
export function Reveal({ children, className, amount = 0.2 }: Props) {
  return (
    <m.div className={className} variants={group} initial="hidden" whileInView="show" viewport={{ once: true, amount }}>
      {children}
    </m.div>
  );
}

export function RevealItem({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <m.div className={className} variants={item}>
      {children}
    </m.div>
  );
}
