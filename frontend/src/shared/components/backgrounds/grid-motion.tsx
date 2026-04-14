"use client";

import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import "./grid-motion.css";

interface GridMotionProps {
  items?: (string | React.ReactNode)[];
  gradientColor?: string;
}

const TOTAL_ITEMS = 28;
const ROWS = 4;
const COLS = 7;

export function GridMotion({
  items = [],
  gradientColor = "oklch(0.14 0.015 255)",
}: GridMotionProps) {
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);
  const mouseXRef = useRef(typeof window !== "undefined" ? window.innerWidth / 2 : 0);

  const cells =
    items.length > 0
      ? items.slice(0, TOTAL_ITEMS)
      : Array.from({ length: TOTAL_ITEMS }, (_, i) => `Item ${i + 1}`);

  useEffect(() => {
    gsap.ticker.lagSmoothing(0);

    const onMouseMove = (e: MouseEvent) => {
      mouseXRef.current = e.clientX;
    };

    const updateMotion = () => {
      const maxMove = 300;
      const baseDuration = 0.8;
      const inertia = [0.6, 0.4, 0.3, 0.2];

      rowRefs.current.forEach((row, i) => {
        if (!row) return;
        const dir = i % 2 === 0 ? 1 : -1;
        const move =
          ((mouseXRef.current / window.innerWidth) * maxMove - maxMove / 2) *
          dir;

        gsap.to(row, {
          x: move,
          duration: baseDuration + inertia[i % inertia.length],
          ease: "power3.out",
          overwrite: "auto",
        });
      });
    };

    const removeTicker = gsap.ticker.add(updateMotion);
    window.addEventListener("mousemove", onMouseMove);

    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      removeTicker();
    };
  }, []);

  return (
    <div className="grid-motion">
      <section
        className="grid-motion__scene"
        style={{
          background: `radial-gradient(circle, ${gradientColor} 0%, transparent 100%)`,
        }}
      >
        <div className="grid-motion__grid">
          {Array.from({ length: ROWS }, (_, rowIdx) => (
            <div
              key={rowIdx}
              className="grid-motion__row"
              ref={(el) => { rowRefs.current[rowIdx] = el; }}
            >
              {Array.from({ length: COLS }, (_, colIdx) => {
                const content = cells[rowIdx * COLS + colIdx];
                return (
                  <div key={colIdx} className="grid-motion__cell">
                    <div className="grid-motion__cell-inner bg-muted/60 text-muted-foreground/60 border border-border/40">
                      {typeof content === "string" &&
                      content.startsWith("http") ? (
                        <div
                          style={{
                            width: "100%",
                            height: "100%",
                            backgroundImage: `url(${content})`,
                            backgroundSize: "cover",
                            backgroundPosition: "center",
                            position: "absolute",
                            inset: 0,
                          }}
                        />
                      ) : (
                        <span style={{ padding: "0.5rem", textAlign: "center" }}>
                          {content}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
