import { CHART_COLORS, GROUP_PALETTE } from "@/shared/lib/chart-colors";
import type { PlateGroupNode } from "../hooks/use-plate-groups";

export const MAX_NODE_LABEL = 28;

/** Legacy plate-tracker palette (spec 2026-08-25 §6); keys are lower-cased. */
export const TYPE_COLORS: Record<string, string> = {
  vendor: "#FFBD50",
  screening: "#8F7EB5",
  master_twin: "#C3D9E4",
  hit_collection: "#E27D60",
};
export const STATE_COLORS: Record<string, string> = {
  solubilized: "#7AB648",
  dry: "#99D2F2",
  retired: "#94a3b8",
};

export const ROOT_STORAGE_KEY = (orgId: string) => `plate-groups.root.${orgId}`;

export interface LegendEntry {
  label: string;
  color: string;
}

/** Fixed legacy color for the four known types; deterministic hash → palette for
 * anything else; neutral for untyped. */
export function groupTypeColor(groupType: string | null | undefined): string {
  if (!groupType) return CHART_COLORS.neutral;
  const fixed = TYPE_COLORS[groupType.toLowerCase()];
  if (fixed) return fixed;
  let hash = 5381;
  for (let i = 0; i < groupType.length; i++) {
    hash = (hash * 33) ^ groupType.charCodeAt(i);
  }
  return GROUP_PALETTE[Math.abs(hash) % GROUP_PALETTE.length];
}

/** Circle fill by state: solubilized green, dry blue, anything else neutral. */
export function stateColor(state: string | null | undefined): string {
  if (!state) return CHART_COLORS.neutral;
  return STATE_COLORS[state.toLowerCase()] ?? CHART_COLORS.neutral;
}

export function formatLabel(fmt: string | null | undefined): string | null {
  if (!fmt) return null;
  return fmt === "mixed" ? "mixed formats" : `${fmt}-well`;
}

export function truncateLabel(name: string, max: number = MAX_NODE_LABEL): string {
  return name.length > max ? `${name.slice(0, max - 1)}…` : name;
}

/** Distinct states and types present in the tree (depth-first, first-seen order)
 * with "unset"/"untyped" appended when any node lacks one. */
export function legendEntries(roots: PlateGroupNode[]): {
  states: LegendEntry[];
  types: LegendEntry[];
} {
  const seenStates = new Set<string>();
  const seenTypes = new Set<string>();
  const states: LegendEntry[] = [];
  const types: LegendEntry[] = [];
  let hasUnset = false;
  let hasUntyped = false;
  const walk = (n: PlateGroupNode) => {
    const state = n.state ?? "";
    if (!state) hasUnset = true;
    else if (!seenStates.has(state.toLowerCase())) {
      seenStates.add(state.toLowerCase());
      states.push({ label: state, color: stateColor(state) });
    }
    const type = n.group_type ?? "";
    if (!type) hasUntyped = true;
    else if (!seenTypes.has(type.toLowerCase())) {
      seenTypes.add(type.toLowerCase());
      types.push({ label: type, color: groupTypeColor(type) });
    }
    for (const c of n.children ?? []) walk(c);
  };
  for (const r of roots) walk(r);
  if (hasUnset) states.push({ label: "unset", color: CHART_COLORS.neutral });
  if (hasUntyped) types.push({ label: "untyped", color: CHART_COLORS.neutral });
  return { states, types };
}
