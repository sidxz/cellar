"use client";

import { useDecompositionRun } from "@/features/sar-analysis/hooks/use-decomposition-run";
import { useScaffoldTree } from "@/features/sar-analysis/hooks/use-scaffold-tree";
import { useUmapCluster } from "@/features/sar-analysis/hooks/use-umap-cluster";
import { useQuery } from "@tanstack/react-query";
import { type Dispatch, useEffect, useMemo, useRef } from "react";
import type { DerivedAction, DerivedEntry } from "../hooks/use-derived";
import { useRGroupAssignments } from "../hooks/use-rgroup-assignments";
import { matchSubstructure } from "../hooks/use-substructure-match";
import { errorText } from "../lib/api-errors";
import type { ViewConfig } from "../lib/config-schema";
import { datasetMoleculeIds } from "../lib/dataset";
import {
  type DerivedSet,
  type DerivedSpec,
  clusterSet,
  rgroupSet,
  seriesSet,
} from "../lib/derived";
import { membershipKey } from "../lib/filters";
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
 * while the entry runs, so unmounting is the cancel. The columns cover the compounds the job
 * ran over: any added to the dataset since stay blank, and the bar offers Recompute. */
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

/** One job per attempt: Retry, Run again or a replacement never reuses an earlier start. */
const nonceOf = (entry: DerivedEntry) => `${entry.spec.id}:${entry.attempt}`;

/** Reports the job's outcome once known. Leaving before an answer (Cancel, ✕, leaving the
 * page) cancels the server job, even one whose start has not answered yet. */
function useOutcome(
  { entry, dispatch }: Props,
  cancel: () => void,
  failure: string | null,
  set: DerivedSet | null,
) {
  const id = entry.spec.id;
  const outcome = useRef<"ready" | "failed" | null>(null);
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
      if (outcome.current === null) latestCancel.current();
    },
    [],
  );
}

function NoCompounds(props: Props) {
  useOutcome(props, () => {}, "No compound in this dataset has a structure.", null);
  return null;
}

function RGroupsRunner(props: Of<"rgroups">) {
  const { entry, ds } = props;
  const run = useDecompositionRun({
    moleculeIds: entry.moleculeIds,
    coreSmiles: entry.spec.coreSmiles,
    nonce: nonceOf(entry),
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
    () =>
      assignments.data && ds
        ? rgroupSet(entry.spec, ds, assignments.data, entry.moleculeIds)
        : null,
    [assignments.data, ds, entry.spec, entry.moleculeIds],
  );
  useOutcome(props, run.cancel, failure, set);
  return null;
}

function ClustersRunner(props: Of<"clusters">) {
  const { entry, ds } = props;
  const umap = useUmapCluster({
    moleculeIds: entry.moleculeIds,
    picker: "butina",
    threshold: entry.spec.threshold,
    enabled: true,
    nonce: nonceOf(entry),
  });
  const set = useMemo(
    () => (umap.result && ds ? clusterSet(entry.spec, ds, umap.result, entry.moleculeIds) : null),
    [umap.result, ds, entry.spec, entry.moleculeIds],
  );
  useOutcome(props, umap.cancel, umap.error && plain(umap.error), set);
  return null;
}

/** Series from R-groups sets only need no job; scaffold members need the scaffold tree. */
function SeriesRunner(props: Of<"series">) {
  const { entry, ds, readySets } = props;
  const needsTree = entry.spec.members.some((m) => m.scaffold);
  const { tree, error } = useScaffoldTree({
    moleculeIds: entry.moleculeIds,
    enabled: needsTree,
    nonce: nonceOf(entry),
  });
  const set = useMemo(
    () =>
      ds && (!needsTree || tree)
        ? seriesSet(entry.spec, ds, tree, readySets, entry.moleculeIds)
        : null,
    [ds, needsTree, tree, entry.spec, readySets, entry.moleculeIds],
  );
  useOutcome(props, () => {}, needsTree && error ? plain(error) : null, set);
  return null;
}

type SavedQuery = Extract<ViewConfig["filters"][number], { kind: "substructure" }>;
/** A saved substructure query matched again: the compounds it matched and the compounds it
 * was matched over, or why it couldn't be. */
export type Rematch = { moleculeIds: string[]; over: string } | { error: string };

/** Matches a saved view's substructure query against the dataset's compounds and reports the
 * outcome; renders nothing. A query is not a job: no cancel. */
export function SubstructureRematch({
  filter,
  ds,
  onDone,
}: {
  filter: SavedQuery;
  ds: Dataset;
  onDone: (id: string, outcome: Rematch) => void;
}) {
  const { query, queryKind } = filter;
  const { data, error } = useQuery({
    queryKey: ["visualization", "substructure-rematch", query, queryKind, ds.revision],
    queryFn: () => matchSubstructure({ query, queryKind, moleculeIds: datasetMoleculeIds(ds) }),
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
  useEffect(() => {
    if (data) onDone(filter.id, { moleculeIds: data.matched_ids, over: membershipKey(ds) });
    else if (error) onDone(filter.id, { error: plain(error) });
  }, [filter.id, data, error, onDone, ds]);
  return null;
}
