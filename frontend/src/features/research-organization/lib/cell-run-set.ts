import type { ActivityValue, ProtocolColumnGroups } from "../types";
import type { ComparisonChannel } from "./comparison-channels";

/** The runs behind a protocol's search cells for one compound. */
export interface ProtocolRunSet {
  /** Every run any of the protocol's cells drew on (non-rejected, in the
   *  search's run filter). */
  runIds: Set<string>;
  /** Split protocols: run id → its group's label ("10 µM", "2026-03-01"). */
  groupLabel: Map<string, string>;
}

/** Each searched protocol's run set, read from the cells the backend sent —
 *  the drawer never re-derives run filters or selection rules itself. */
export function protocolRunSets(
  activity: Record<string, ActivityValue> | undefined,
  channels: readonly ComparisonChannel[],
  columnGroups: Record<string, ProtocolColumnGroups> | null | undefined,
): Map<string, ProtocolRunSet> {
  const out = new Map<string, ProtocolRunSet>();
  for (const channel of channels) {
    const set = out.get(channel.protocolId) ?? { runIds: new Set(), groupLabel: new Map() };
    out.set(channel.protocolId, set);
    const groups = columnGroups?.[channel.protocolId]?.groups;
    const cells = groups
      ? groups.map((g) => ({ av: activity?.[`${channel.activityKey}@${g.key}`], label: g.label }))
      : [{ av: activity?.[channel.activityKey], label: null }];
    for (const { av, label } of cells) {
      for (const runId of av?.run_ids ?? []) {
        set.runIds.add(runId);
        if (label) set.groupLabel.set(runId, label);
      }
    }
  }
  return out;
}
