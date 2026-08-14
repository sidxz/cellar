import { CHART_COLORS, GROUP_PALETTE } from "@/shared/lib/chart-colors";
import type { PlateGroupNode } from "../hooks/use-plate-groups";

export const MAX_NODE_LABEL = 28;

/** Deterministic string hash → palette color; free-text group types get a
 * stable color across renders/sessions. Untyped groups stay neutral. */
export function groupTypeColor(groupType: string): string {
  if (!groupType) return CHART_COLORS.neutral;
  let hash = 5381;
  for (let i = 0; i < groupType.length; i++) {
    hash = (hash * 33) ^ groupType.charCodeAt(i);
  }
  return GROUP_PALETTE[Math.abs(hash) % GROUP_PALETTE.length];
}

export function truncateLabel(name: string, max: number = MAX_NODE_LABEL): string {
  return name.length > max ? `${name.slice(0, max - 1)}…` : name;
}

/** Distinct group types present in the tree (deterministic depth-first order) for the legend. */
export function legendEntries(roots: PlateGroupNode[]): { label: string; color: string }[] {
  const seen = new Set<string>();
  let hasUntyped = false;
  const entries: { label: string; color: string }[] = [];
  const stack = [...roots];
  while (stack.length > 0) {
    const node = stack.pop() as PlateGroupNode;
    const type = node.group_type ?? "";
    if (!type) hasUntyped = true;
    else if (!seen.has(type)) {
      seen.add(type);
      entries.push({ label: type, color: groupTypeColor(type) });
    }
    stack.push(...(node.children ?? []));
  }
  if (hasUntyped) entries.push({ label: "untyped", color: CHART_COLORS.neutral });
  return entries;
}
