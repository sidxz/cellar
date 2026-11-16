"use client";

import { useDecompositionRun } from "@/features/sar-analysis/hooks/use-decomposition-run";
import { useScaffoldTree } from "@/features/sar-analysis/hooks/use-scaffold-tree";
import { useUmapCluster } from "@/features/sar-analysis/hooks/use-umap-cluster";
import { useQueryClient } from "@tanstack/react-query";
import { type Dispatch, useEffect, useMemo, useRef } from "react";
import type { DerivedAction, DerivedEntry } from "../hooks/use-derived";
import { useRGroupAssignments } from "../hooks/use-rgroup-assignments";
import { errorText } from "../lib/api-errors";
import {
  type DerivedSet,
  type DerivedSpec,
  clusterSet,
  rgroupSet,
  seriesSet,
} from "../lib/derived";
import type { Dataset } from "../types";

type Props = {
  entry: DerivedEntry;
  /** The loaded data (none while a level switch loads; the columns wait for it). */
  ds: Dataset | undefined;
  readySets: DerivedSet[];
  dispatch: Dispatch<DerivedAction>;
};
type Of<K extends DerivedSpec["kind"]> = Props & {
  entry: DerivedEntry & { spec: Extract<DerivedSpec, { kind: K }> };
};

/** The server's sentence, without the client's "API error: 400 — " wrapping. */
const plain = (error: unknown) =>
  (typeof error === "string" ? error : errorText(error)).replace(/^.*API error: \d+ — /, "");

/** Runs one entry's job and reports its columns or its failure; renders nothing. Mounted
 * while the entry runs, so unmounting is the cancel. */
export function DerivedRunner(props: Props) {
  if (props.entry.moleculeIds.length === 0) return <NoCompounds {...props} />;
  switch (props.entry.spec.kind) {
    case "rgroups":
      return <RGroupsRunner {...(props as Of<"rgroups">)} />;
    case "clusters":
      return <ClustersRunner {...(props as Of<"clusters">)} />;
    case "series":
      return <SeriesRunner {...(props as Of<"series">)} />;
  }
}

/** Reports the job's outcome once known. Leaving before an answer (Cancel, ✕, leaving the
 * page) cancels the server job; leaving without columns also forgets the job's cached
 * start (`startKey`, the job hook's query key), so Retry starts a fresh job. */
function useOutcome(
  { entry, dispatch }: Props,
  startKey: string | null,
  cancel: () => void,
  failure: string | null,
  set: DerivedSet | null,
) {
  const id = entry.spec.id;
  const outcome = useRef<"ready" | "failed" | null>(null);
  const queryClient = useQueryClient();
  const latestCancel = useRef(cancel);
  latestCancel.current = cancel;

  useEffect(() => {
    if (failure) {
      outcome.current = "failed";
      dispatch({ type: "fail", id, message: failure });
    } else if (set) {
      outcome.current = "ready";
      dispatch({ type: "resolve", id, set });
    }
  }, [id, failure, set, dispatch]);

  useEffect(
    () => () => {
      if (outcome.current === "ready") return;
      if (outcome.current === null) latestCancel.current();
      if (startKey === null) return;
      // Once this unmount has unsubscribed the job's queries.
      setTimeout(() =>
        queryClient.removeQueries({ queryKey: [startKey, "start"], type: "inactive" }),
      );
    },
    [queryClient, startKey],
  );
}

function NoCompounds(props: Props) {
  useOutcome(props, null, () => {}, "No compound in this dataset has a structure.", null);
  return null;
}

function RGroupsRunner(props: Of<"rgroups">) {
  const { entry, ds } = props;
  const run = useDecompositionRun({
    moleculeIds: entry.moleculeIds,
    coreSmiles: entry.spec.coreSmiles,
  });
  const done = run.status === "ready";
  const none = done && run.counts?.matched === 0;
  const assignments = useRGroupAssignments(done && !none ? run.runId : null);
  const error = run.error ?? assignments.error;
  let failure: string | null = null;
  if (error) failure = plain(error);
  else if (none) failure = "No compound in this dataset matches the core.";
  else if (run.isCancelled) failure = "The job was cancelled.";
  const set = useMemo(
    () => (assignments.data && ds ? rgroupSet(entry.spec, ds, assignments.data) : null),
    [assignments.data, ds, entry.spec],
  );
  useOutcome(props, "decomposition-run", run.cancel, failure, set);
  return null;
}

function ClustersRunner(props: Of<"clusters">) {
  const { entry, ds } = props;
  const umap = useUmapCluster({
    moleculeIds: entry.moleculeIds,
    picker: "butina",
    threshold: entry.spec.threshold,
    enabled: true,
  });
  const set = useMemo(
    () => (umap.result && ds ? clusterSet(entry.spec, ds, umap.result) : null),
    [umap.result, ds, entry.spec],
  );
  useOutcome(props, "umap-cluster", umap.cancel, umap.error && plain(umap.error), set);
  return null;
}

/** Series from R-groups sets only need no job; scaffold members need the scaffold tree. */
function SeriesRunner(props: Of<"series">) {
  const { entry, ds, readySets } = props;
  const needsTree = entry.spec.members.some((m) => m.scaffold);
  const { tree, error } = useScaffoldTree({ moleculeIds: entry.moleculeIds, enabled: needsTree });
  const set = useMemo(
    () => (ds && (!needsTree || tree) ? seriesSet(entry.spec, ds, tree, readySets) : null),
    [ds, needsTree, tree, entry.spec, readySets],
  );
  useOutcome(props, "scaffold-tree", () => {}, needsTree && error ? plain(error) : null, set);
  return null;
}
