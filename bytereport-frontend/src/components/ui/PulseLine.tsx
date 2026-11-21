import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { WeeklyCashFlow } from "@/types";

interface Props {
  data: WeeklyCashFlow[];
  height?: number;
  /** Dim the line so it sits behind content. The peak marker stays readable. */
  decorative?: boolean;
  /** Draw the line when this flips to true. Defaults to drawing on mount. */
  active?: boolean;
  /** Draw duration in ms — match this to any counter animating alongside it. */
  duration?: number;
  className?: string;
}

const PAD_X = 8;
const PAD_Y = 10;
const DOT_R = 6;

export function PulseLine({
  data,
  height = 56,
  decorative = false,
  active = true,
  duration = 1400,
  className,
}: Props) {
  const uid = useRef(`pl-${Math.random().toString(36).slice(2)}`).current;
  const hostRef = useRef<HTMLDivElement>(null);
  const clipRef = useRef<SVGRectElement>(null);
  const frameRef = useRef(0);
  const [width, setWidth] = useState(0);
  const [dotIn, setDotIn] = useState(false);

  // Measure in real pixels. The previous version stretched a fixed viewBox with
  // preserveAspectRatio="none", which squashed the peak dot into an ellipse.
  useLayoutEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    setWidth(el.getBoundingClientRect().width);
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const rect = clipRef.current;
    if (!rect || !width) return;

    if (!active) {
      rect.setAttribute("width", "0");
      setDotIn(false);
      return;
    }

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      rect.setAttribute("width", String(width));
      setDotIn(true);
      return;
    }

    const start = performance.now();
    const tick = (now: number) => {
      // Clamp both ends: a rAF timestamp can predate `start` (it reports the
      // frame's begin time), which would make t negative and the eased value
      // negative with it — SVG rejects a negative rect width.
      const t = Math.min(Math.max((now - start) / duration, 0), 1);
      const eased = 1 - (1 - t) ** 3;
      rect.setAttribute("width", String(eased * width));
      if (t < 1) frameRef.current = requestAnimationFrame(tick);
      else setDotIn(true);
    };
    setDotIn(false);
    frameRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameRef.current);
  }, [active, width, duration]);

  if (data.length < 2) return null;

  const nets = data.map((d) => d.net);
  const minNet = Math.min(...nets);
  const maxNet = Math.max(...nets);
  const range = maxNet - minNet || 1;
  const maxIdx = nets.indexOf(maxNet);

  const px = (i: number) => PAD_X + (i / (data.length - 1)) * (width - 2 * PAD_X);
  const py = (v: number) => PAD_Y + (1 - (v - minNet) / range) * (height - 2 * PAD_Y);

  return (
    <div ref={hostRef} className={className} style={{ height }}>
      {width > 0 && (
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
          <defs>
            <clipPath id={`${uid}-clip`}>
              <rect ref={clipRef} x="0" y="0" width="0" height={height} />
            </clipPath>
            {/* The only glow in the product, reserved for the peak-week marker.
                Softened after the redesign: at stdDeviation 3.5 plus a full
                merge it was the loudest element on the chart, which is not
                what a single data point should be. */}
            <filter id={`${uid}-glow`} x="-120%" y="-120%" width="340%" height="340%">
              <feGaussianBlur stdDeviation="1.6" result="blur" />
              <feComponentTransfer in="blur" result="soft">
                <feFuncA type="linear" slope="0.45" />
              </feComponentTransfer>
              <feMerge>
                <feMergeNode in="soft" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Cash-flow trace. Dimmed when decorative so it never fights the copy,
              but stays well above the "have to squint" threshold. */}
          <g clipPath={`url(#${uid}-clip)`} opacity={decorative ? 0.6 : 1}>
            {data.slice(0, -1).map((_, i) => {
              const nextNet = data[i + 1].net;
              return (
                <line
                  key={i}
                  x1={px(i)} y1={py(data[i].net)}
                  x2={px(i + 1)} y2={py(nextNet)}
                  stroke={nextNet >= 0 ? "var(--color-success)" : "var(--color-danger)"}
                  strokeWidth={2.5}
                  strokeLinecap="round"
                />
              );
            })}
          </g>

          {/* Peak cash week — the accent marks a data event, never decoration. */}
          <g
            style={{
              opacity: dotIn ? 1 : 0,
              transition: "opacity 320ms ease-out",
            }}
          >
            <circle
              cx={px(maxIdx)} cy={py(maxNet)} r={DOT_R * 1.6}
              fill="var(--color-accent)" opacity={0.10}
            />
            <circle
              cx={px(maxIdx)} cy={py(maxNet)} r={DOT_R}
              fill="var(--color-accent)"
              stroke="var(--color-ground)" strokeWidth={1.5}
              filter={`url(#${uid}-glow)`}
            />
          </g>
        </svg>
      )}
    </div>
  );
}
