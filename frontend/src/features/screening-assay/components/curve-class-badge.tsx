"use client";

/**
 * Shared curve-class badge used by the protocol Activity tab, the campaign
 * results grid, search results, and the run DR results panel. Centralises
 * the color tokens so "Inactive" no longer collides with the Badge default
 * variant (which was rendering as solid `bg-primary` and producing the
 * dark-blue-on-dark-blue unreadable chip a chemist flagged).
 *
 * Render modes:
 *   - `compact={false}` (default) — full word ("Full" / "Partial" / "Inactive" / "Bell Shaped").
 *   - `compact={true}`            — single-letter abbreviation, inline next
 *                                   to a value cell where space is tight.
 *
 * Color tokens (kept in lock-step with the rest of the assay UI):
 *   full         → success green
 *   partial      → warning yellow
 *   bell_shaped  → primary blue
 *   inactive     → neutral slate (outlined, transparent bg) — readable in
 *                  both light and dark themes
 */

import { Badge } from "@/shared/components/ui/badge";
import { CURVE_CLASS_LABELS, type CurveClass } from "../types";

const FULL_STYLES: Record<string, string> = {
  full: "border-success/40 bg-success/10 text-success",
  partial: "border-yellow-500/40 bg-yellow-500/10 text-yellow-400",
  bell_shaped: "border-primary/40 bg-primary/10 text-primary",
  inactive:
    "border-slate-300 bg-transparent text-slate-700 dark:border-slate-600 dark:text-slate-300",
};

const COMPACT_STYLES: Record<string, string> = {
  full: "bg-success/15 text-success",
  partial: "bg-yellow-500/15 text-yellow-400",
  bell_shaped: "bg-primary/15 text-primary",
  inactive: "bg-slate-200/60 text-slate-700 dark:bg-slate-800/40 dark:text-slate-300",
};

interface CurveClassBadgeProps {
  curveClass: CurveClass | string | null | undefined;
  /** Compact (single-letter) inline form used in tight cells. */
  compact?: boolean;
  /** Whether to render a "--" placeholder when curveClass is missing.
   *  Default keeps the placeholder so the column stays aligned; pass
   *  "nothing" when the host already renders its own no-data fallback. */
  renderNullAs?: "dash" | "nothing";
  className?: string;
}

export function CurveClassBadge({
  curveClass,
  compact = false,
  renderNullAs = "dash",
  className,
}: CurveClassBadgeProps) {
  if (!curveClass) {
    if (renderNullAs === "nothing") return null;
    return (
      <Badge
        variant="outline"
        className={`text-muted-foreground${className ? ` ${className}` : ""}`}
      >
        --
      </Badge>
    );
  }

  const key = String(curveClass).toLowerCase();
  if (compact) {
    const cls = COMPACT_STYLES[key] ?? COMPACT_STYLES.inactive;
    const letter = key.charAt(0).toUpperCase();
    return (
      <Badge
        className={`ml-1.5 text-[10px] px-1 py-0 border-0 ${cls}${
          className ? ` ${className}` : ""
        }`}
      >
        {letter}
      </Badge>
    );
  }

  const cls = FULL_STYLES[key] ?? FULL_STYLES.inactive;
  const label = (CURVE_CLASS_LABELS as Record<string, string>)[curveClass] ?? curveClass;
  return (
    <Badge variant="outline" className={`${cls}${className ? ` ${className}` : ""}`}>
      {label}
    </Badge>
  );
}
