"use client";

import { StructureEditorDialog, StructureRenderer } from "@/shared/components/chemistry";
import { Alert } from "@/shared/components/ui/alert";
import { Button } from "@/shared/components/ui/button";
import { Loader2, Pencil, RefreshCw, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useSubstructureMatch } from "../../hooks/use-substructure-match";
import { errorText } from "../../lib/api-errors";
import { datasetMoleculeIds, noStructureCompounds } from "../../lib/dataset";
import { type Filter, type SubstructureFilter, substructureCounts } from "../../lib/filters";
import { useWorkbench } from "../../store/workbench-context";
import type { Dataset } from "../../types";
import { FilterCard } from "./filter-card";

/** "sub-1", "sub-2", …: the first one no filter uses. */
function nextId(filters: Filter[]): string {
  let n = 1;
  while (filters.some((f) => f.id === `sub-${n}`)) n += 1;
  return `sub-${n}`;
}

/** Matching a query against every compound of the dataset, then adding the filter (or,
 * with ``filter``, replacing its query and matches under the same id) in one undo step. */
function useApplyQuery(ds: Dataset, filter?: SubstructureFilter) {
  const filters = useWorkbench((s) => s.filters);
  const upsertFilter = useWorkbench((s) => s.upsertFilter);
  const match = useSubstructureMatch();

  const apply = (query: string, queryKind: "smiles" | "smarts") => {
    const id = filter?.id ?? nextId(filters);
    match.mutate(
      { query, queryKind, moleculeIds: datasetMoleculeIds(ds) },
      {
        onSuccess: (res) => {
          upsertFilter({
            id,
            kind: "substructure",
            query,
            queryKind,
            moleculeIds: res.matched_ids,
          });
          match.reset();
        },
      },
    );
  };
  return { match, apply };
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
        initialStructure={match.variables?.query ?? filter?.query}
        onApply={apply}
      />
      <MatchStatus match={match} onEdit={() => onOpenChange(true)} />
    </>
  );
}

/** A filter opened from a saved view, not matched against this data yet: "Match again" runs
 * its saved query. */
function MatchAgain({
  ds,
  filter,
  onEdit,
}: {
  ds: Dataset;
  filter: SubstructureFilter;
  onEdit: () => void;
}) {
  const { match, apply } = useApplyQuery(ds, filter);
  return (
    <>
      <Button
        size="sm"
        variant="outline"
        className="h-6 px-2 text-xs"
        disabled={match.isPending}
        onClick={() => apply(filter.query, filter.queryKind)}
      >
        <RefreshCw className="h-3 w-3" />
        Match again
      </Button>
      {(match.isPending || match.isError) && (
        <div className="basis-full">
          <MatchStatus match={match} onEdit={onEdit} />
        </div>
      )}
    </>
  );
}

/** A substructure filter: the query drawn as a structure, how many of the dataset's
 * compounds contain it (a warning when none do, or when it is not matched against this
 * data yet — then "Match again"), the compounds that cannot match for lack of a structure,
 * and Edit, which re-matches under the same filter. */
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
          {!filter.moleculeIds ? (
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
            {!filter.moleculeIds && (
              <MatchAgain ds={ds} filter={filter} onEdit={() => setEditing(true)} />
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
