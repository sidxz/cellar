"use client";

import type { ReactNode } from "react";

/**
 * Labeled placeholder box rendered by every widget STUB until the real
 * implementation lands. Keeps a consistent footprint so MDX pages embedding
 * widgets look reasonable before the widget-builder agents fill them in.
 */
export function WidgetPlaceholder({
  name,
  details,
  minHeight = 220,
}: {
  name: string;
  details?: ReactNode;
  minHeight?: number;
}) {
  return (
    <div
      role="group"
      aria-label={`${name} (placeholder)`}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "0.5rem",
        minHeight,
        padding: "1.25rem",
        margin: "1rem 0",
        border: "1px dashed currentColor",
        borderRadius: "0.5rem",
        opacity: 0.7,
        textAlign: "center",
        fontSize: "0.875rem",
      }}
    >
      <strong style={{ fontSize: "0.95rem" }}>🧪 {name}</strong>
      <span>Interactive widget — placeholder (implementation pending)</span>
      {details ? <span style={{ opacity: 0.85 }}>{details}</span> : null}
    </div>
  );
}
