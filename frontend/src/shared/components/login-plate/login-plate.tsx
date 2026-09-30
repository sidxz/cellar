"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import "./login-plate.css";
import { mulberry32, noiseWells, tracePoints, vars } from "./lib";

/** Well pitch in px; the plate is drawn 1:1 and sized to its container. */
const PITCH = 28;
const RADIUS = 7;
/** The dose-response curves that take turns lighting up across the plate. */
const CURVES = [
  { dx: -0.14, k: 1.5 },
  { dx: 0.1, k: 2 },
  { dx: -0.02, k: 1.2 },
];
/** Share of wells that glow on their own, as noise. */
const NOISE = 0.015;

/**
 * A screening plate that fills the page edge to edge, and the hit in it: the
 * wells that lie on a dose-response sigmoid glow in a sweep from low dose to
 * high, hold, and fade while the next curve starts. The trace is imperfect
 * and a few wells twinkle as noise, like a real read. The wells wave in on
 * mount; reduced motion shows the plate still.
 */
export function LoginPlate({ panel = 460 }: { panel?: number }) {
  const host = useRef<HTMLDivElement>(null);
  const [grid, setGrid] = useState({ rows: 0, cols: 0 });
  const [phase, setPhase] = useState<"" | "anim" | "anim is-in">("");

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setGrid({ rows: Math.ceil(height / PITCH), cols: Math.ceil(width / PITCH) });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // wave in once, after the first measured render
  useEffect(() => {
    if (!grid.rows || phase || window.matchMedia("(prefers-reduced-motion: reduce)").matches)
      return;
    setPhase("anim");
    const raf = requestAnimationFrame(() => requestAnimationFrame(() => setPhase("anim is-in")));
    return () => cancelAnimationFrame(raf);
  }, [grid.rows, phase]);

  const { traces, noise } = useMemo(() => {
    const random = mulberry32(5);
    return {
      traces: CURVES.map((curve) =>
        tracePoints(grid.rows, grid.cols, PITCH, panel, curve, 3, random),
      ),
      noise: noiseWells(
        grid.rows,
        grid.cols,
        PITCH,
        panel,
        Math.round(grid.rows * grid.cols * NOISE),
        random,
      ),
    };
  }, [grid, panel]);

  return (
    <div ref={host} className={`login-plate ${phase}`}>
      {grid.rows > 0 && (
        <svg width={grid.cols * PITCH} height={grid.rows * PITCH} aria-hidden="true">
          {Array.from({ length: grid.cols }, (_, c) => (
            <g key={c} style={vars({ "--c": c })}>
              {Array.from({ length: grid.rows }, (_, r) => (
                <circle
                  key={r}
                  cx={c * PITCH + PITCH / 2}
                  cy={r * PITCH + PITCH / 2}
                  r={RADIUS}
                  style={vars({ "--r": r })}
                />
              ))}
            </g>
          ))}
          {/* the hit and the noise, lit by the CSS */}
          <g className="trace">
            {traces.map((points, g) =>
              points.map(([r, c, i]) => (
                <circle
                  key={`${g}:${r}:${c}`}
                  cx={c * PITCH + PITCH / 2}
                  cy={r * PITCH + PITCH / 2}
                  r={RADIUS + 1}
                  style={vars({ "--g": g, "--i": i })}
                />
              )),
            )}
            {noise.map(([r, c, p]) => (
              <circle
                key={`n:${r}:${c}`}
                className="noise"
                cx={c * PITCH + PITCH / 2}
                cy={r * PITCH + PITCH / 2}
                r={RADIUS + 1}
                style={vars({ "--p": p })}
              />
            ))}
          </g>
        </svg>
      )}
    </div>
  );
}
