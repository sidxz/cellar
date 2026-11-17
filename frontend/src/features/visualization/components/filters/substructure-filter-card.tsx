"use client";

import { StructureEditorDialog, StructureRenderer } from "@/shared/components/chemistry";
import { Alert } from "@/shared/components/ui/alert";
import { Button } from "@/shared/components/ui/button";
import { Loader2, Pencil, RefreshCw, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSubstructureMatch } from "../../hooks/use-substructure-match";
import { errorText } from "../../lib/api-errors";
import { datasetMoleculeIds, noStructureCompounds } from "../../lib/dataset";
import {
  type SubstructureFilter,
  matchedIds,
  membershipKey,
  substructureCounts,
} from "../../lib/filters";
import { useWorkbench } from "../../store/workbench-context";
import type { Dataset } from "../../types";
import { FilterCard } from "./filter-card";

let seq = 0;

/** Matching a query against every compound of the dataset, then adding the filter (or,
 * with ``filter``, replacing its query and matches under the same id) in one undo step.
 * Each add has its own id from the start, so two drawn before the first matched both land. */
function useApplyQuery(ds: Dataset, filter?: SubstructureFilter) {
  const upsertFilter = useWorkbench((s) => s.upsertFilter);
  const match = useSubstructureMatch();

  const apply = (query: string, queryKind: "smiles" | "smarts") => {
    seq += 1;
    const id = filter?.id ?? `sub-${Date.now().toString(36)}-${seq}`;
    const over = membershipKey(ds);
    match.mutateAsync({ query, queryKind, moleculeIds: datasetMoleculeIds(ds) }).then(
      (res) =>
        upsertFilter({
          id,
          kind: "substructure",
          query,
          queryKind,
          moleculeIds: res.matched_ids,
          over,
        }),
      // MatchStatus shows the failure.
      () => {},
    );
  };
  return { match, apply };
}

/** The filter's own query matched again over this dataset's compounds (when they are not
 * the ones it was matched over, it does so by itself): not an undo step, as the chemist
 * changed nothing; dropped if the filter changed meanwhile. */
function useMatchAgain(ds: Dataset, filter: SubstructureFilter) {
  const replaceFilter = useWorkbench((s) => s.replaceFilter);
  const match = useSubstructureMatch();
  const { mutate } = match;
  const over = membershipKey(ds);
  const again = () =>
    mutate(
      { query: filter.query, queryKind: filter.queryKind, moleculeIds: datasetMoleculeIds(ds) },
      {
        onSuccess: (res) =>
          replaceFilter(filter, { ...filter, moleculeIds: res.matched_ids, over }),
      },
    );
  const stale = filter.moleculeIds !== undefined && filter.over !== over;
  // biome-ignore lint/correctness/useExhaustiveDependencies: once per change of compounds
  useEffect(() => {
    if (stale) again();
  }, [stale, over]);
  return { match, again };
}

/** "Matching…" while the match runs; an unreadable query shows the server's message (and
 * changes no filter) with "Edit query". */
function MatchStatus({
  match,
  onEdit,
}: {
  match: ReturnType<typeof useApplyQuery>["match"];
  onEdit: () => void;
}) {
  return (
    <>
      {match.isPending && (
        <output className="flex items-center gap-2 rounded-md border bg-card px-2 py-1.5 text-sm text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Matching…
        </output>
      )}
      {match.isError && (
        <Alert variant="destructive" className="flex items-start gap-2 px-2 py-1.5 text-xs">
          <div className="min-w-0 flex-1 space-y-1">
            <p>{errorText(match.error)}</p>
            <Button size="sm" variant="outline" className="h-6 px-2 text-xs" onClick={onEdit}>
              Edit query
            </Button>
          </div>
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6 shrink-0"
            aria-label="Dismiss"
            onClick={() => match.reset()}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </Alert>
      )}
    </>
  );
}

/** The structure editor and the server match behind it: applying a drawing matches it (see
 * ``useApplyQuery``). */
export function SubstructureQuery({
  ds,
  filter,
  open,
  onOpenChange,
}: {
  ds: Dataset;
  filter?: SubstructureFilter;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { match, apply } = useApplyQuery(ds, filter);
  return (
    <>
      <StructureEditorDialog
        open={open}
        onOpenChange={onOpenChange}
        outputFormat="auto"
        // After a failure, the query that failed (Edit query); else the filter's.
        initialStructure={(match.isError ? match.variables?.query : undefined) ?? filter?.query}
        onApply={apply}
      />
      <MatchStatus match={match} onEdit={() => onOpenChange(true)} />
    </>
  );
}

/** A substructure filter: the query drawn as a structure, how many of the dataset's
 * compounds contain it (a warning when none do, or when it is not matched against this
 * data yet — then "Match again"; matched over other compounds, it matches again by
 * itself), the compounds that cannot match for lack of a structure, and Edit, which
 * re-matches under the same filter. */
export function SubstructureFilterCard({
  ds,
  filter,
  active,
}: {
  ds: Dataset;
  filter: SubstructureFilter;
  active: boolean;
}) {
  const [editing, setEditing] = useState<boolean | null>(null);
  // Mounted with the card, collapsed or not, so a stale match never waits on the chemist.
  const { match, again } = useMatchAgain(ds, filter);
  const matchedNow = matchedIds(ds, filter) !== undefined;
  const { matched, total } = useMemo(() => substructureCounts(ds, filter), [ds, filter]);
  const { noStructure, hidesRows } = useMemo(
    () => ({
      noStructure: noStructureCompounds(ds),
      hidesRows: (ds.values.molecule_id ?? []).some((v) => typeof v !== "string"),
    }),
    [ds],
  );

  return (
    <FilterCard ds={ds} filter={filter} active={active}>
      <div className="flex items-start gap-2">
        <StructureRenderer
          smiles={filter.query}
          queryKind={filter.queryKind}
          width={96}
          height={72}
          className="shrink-0 rounded border"
        />
        <div className="min-w-0 flex-1 space-y-1.5 text-xs">
          {match.isPending ? null : !matchedNow ? (
            <p className="rounded border border-warning/30 bg-warning/10 px-1.5 py-1 font-medium text-warning">
              Not matched against this data yet — it filters nothing until matched.
            </p>
          ) : matched === 0 ? (
            <p className="rounded border border-warning/30 bg-warning/10 px-1.5 py-1 font-medium text-warning">
              No compounds contain this substructure
            </p>
          ) : (
            <p>
              {matched.toLocaleString()} of {total.toLocaleString()} compounds match
            </p>
          )}
          <div className="flex flex-wrap gap-1">
            {!matchedNow && (
              <Button
                size="sm"
                variant="outline"
                className="h-6 px-2 text-xs"
                disabled={match.isPending}
                onClick={again}
              >
                <RefreshCw className="h-3 w-3" />
                Match again
              </Button>
            )}
            <Button
              size="sm"
              variant="outline"
              className="h-6 px-2 text-xs"
              onClick={() => setEditing(true)}
            >
              <Pencil className="h-3 w-3" />
              Edit
            </Button>
            {(match.isPending || match.isError) && (
              <div className="basis-full">
                <MatchStatus match={match} onEdit={() => setEditing(true)} />
              </div>
            )}
          </div>
        </div>
      </div>
      <p className="break-all font-mono text-[11px] text-muted-foreground">{filter.query}</p>
      {noStructure > 0 && (
        <p className="text-xs text-muted-foreground">
          {noStructure === 1
            ? "1 compound has no structure and never matches"
            : `${noStructure.toLocaleString()} compounds have no structure and never match`}
        </p>
      )}
      {hidesRows && (
        <p className="text-xs text-muted-foreground">
          Rows without a compound (controls, blanks) are hidden while this is on.
        </p>
      )}
      {editing !== null && (
        <SubstructureQuery ds={ds} filter={filter} open={editing} onOpenChange={setEditing} />
      )}
    </FilterCard>
  );
}
