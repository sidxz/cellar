/**
 * Pick-list badge color palette + hash-derived auto-color fallback.
 *
 * The palette is fixed at 8 entries so chemists never see two near-
 * identical greens. The picker UI (`PickListEditor`) lets users assign
 * one of these per value, or leave color=null to fall back to a stable
 * hash-derived choice from the same palette. Either way the rendered
 * badge always picks from the same 8 swatches end-to-end.
 *
 * Each entry carries:
 *   - hex   : the canonical color stored on PickListValue.color
 *   - bg    : Tailwind bg+border classes for the badge
 *   - text  : Tailwind text class for the badge label
 *   - dot   : Tailwind bg class for a small swatch dot in the picker
 */

export interface PickListColor {
  /** Lowercase 7-char hex — the canonical key stored on PickListValue.color. */
  hex: string;
  /** Display name (en) — shown in the picker tooltip. */
  name: string;
  /** Badge background + border (dark-mode-tuned). */
  bg: string;
  /** Badge text. */
  text: string;
  /** Solid color dot for picker swatches. */
  dot: string;
}

export const PICK_LIST_COLORS: readonly PickListColor[] = [
  {
    hex: "#22c55e",
    name: "Green",
    bg: "bg-green-500/15 border-green-500/40",
    text: "text-green-300",
    dot: "bg-green-500",
  },
  {
    hex: "#ef4444",
    name: "Red",
    bg: "bg-red-500/15 border-red-500/40",
    text: "text-red-300",
    dot: "bg-red-500",
  },
  {
    hex: "#eab308",
    name: "Yellow",
    bg: "bg-yellow-500/15 border-yellow-500/40",
    text: "text-yellow-300",
    dot: "bg-yellow-500",
  },
  {
    hex: "#3b82f6",
    name: "Blue",
    bg: "bg-blue-500/15 border-blue-500/40",
    text: "text-blue-300",
    dot: "bg-blue-500",
  },
  {
    hex: "#a855f7",
    name: "Purple",
    bg: "bg-purple-500/15 border-purple-500/40",
    text: "text-purple-300",
    dot: "bg-purple-500",
  },
  {
    hex: "#f97316",
    name: "Orange",
    bg: "bg-orange-500/15 border-orange-500/40",
    text: "text-orange-300",
    dot: "bg-orange-500",
  },
  {
    hex: "#ec4899",
    name: "Pink",
    bg: "bg-pink-500/15 border-pink-500/40",
    text: "text-pink-300",
    dot: "bg-pink-500",
  },
  {
    hex: "#64748b",
    name: "Slate",
    bg: "bg-slate-500/15 border-slate-500/40",
    text: "text-slate-300",
    dot: "bg-slate-500",
  },
] as const;

const HEX_TO_COLOR: Record<string, PickListColor> = Object.fromEntries(
  PICK_LIST_COLORS.map((c) => [c.hex, c]),
);

/** Stable hash for a label → palette index. djb2-ish, fine for our scale. */
function hashLabel(label: string): number {
  let h = 5381;
  for (let i = 0; i < label.length; i++) {
    h = ((h << 5) + h + label.charCodeAt(i)) >>> 0;
  }
  return h % PICK_LIST_COLORS.length;
}

/** Resolve a label + optional color hex to one of the palette entries.
 *  Unknown hex → falls back to hash. Null/undefined hex → hash. */
export function resolvePickListColor(
  label: string,
  color?: string | null,
): PickListColor {
  if (color) {
    const found = HEX_TO_COLOR[color.toLowerCase()];
    if (found) return found;
  }
  return PICK_LIST_COLORS[hashLabel(label)];
}
