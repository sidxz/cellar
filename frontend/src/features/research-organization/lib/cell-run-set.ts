import type { ActivityValue, ProtocolColumnGroups } from "../types";
import type { ComparisonChannel } from "./comparison-channels";

/** The runs behind a protocol's search cells for one compound. */
export interface ProtocolRunSet {
  /** Every run any of the protocol's cells drew on (non-rejected, in the
   *  search's run filter). */
  runIds: Set<string>;
  /** Condition splits: run id → its group's label ("10 µM"). A run split's
   *  label is the run date the curve already shows, so it isn't repeated. */
  groupLabel: Map<string, string>;
  /** The protocol is split: its values live per group in the grid. */
  split: boolean;
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
    const split = columnGroups?.[channel.protocolId];
    const set = out.get(channel.protocolId) ?? {
      runIds: new Set(),
      groupLabel: new Map(),
      split: !!split,
    };
    out.set(channel.protocolId, set);
    const groups = split?.groups;
    const labelled = split?.split.by === "condition";
    const cells = groups
      ? groups.map((g) => ({
          av: activity?.[`${channel.activityKey}@${g.key}`],
          label: labelled ? g.label : null,
        }))
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

/** The split group of a clicked grid column, when the column is one of this
 *  protocol's: `drc:<readout>…@<group>` or `rd:<protocol>:<readout>…@<group>`.
 *  Null for any other column and for the overlay plot, which holds every
 *  group. */
export function focusedGroupKey(
  colId: string | null | undefined,
  protocol: { id: string; readout_definitions?: readonly { id: string }[] | null },
): string | null {
  if (!colId) return null;
  const [base, ...rest] = colId.split("@");
  const key = rest.join("@");
  if (!key || key === "overlay") return null;
  const parts = base.split(":");
  const owns =
    parts[0] === "rd"
      ? parts[1] === protocol.id
      : parts[0] === "drc" && !!protocol.readout_definitions?.some((r) => r.id === parts[1]);
  return owns ? key : null;
}
