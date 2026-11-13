"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { consumeScaffoldSearch } from "@/features/research-organization/lib/scaffold-search-handoff";
import { CompoundCurvesProvider } from "@/features/screening-assay/components/compound-curves-dialog";
import { useProtocols } from "@/features/screening-assay/hooks/use-protocols";
import { useTags } from "@/features/tagging/hooks/use-tags";
import { CollectionPickerDialog } from "@/shared/components/collection-picker-dialog";
import type { ExportFormat, ExportRequest } from "@/shared/components/export/types";
import { Button } from "@/shared/components/ui/button";
import { AlertCircle, Loader2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { useCollections } from "../hooks/use-collections";
import { useProjects } from "../hooks/use-projects";
import { useReportConfig } from "../hooks/use-report-config";
import { useSavedSearches } from "../hooks/use-saved-searches";
import { type EnrichedSearchResponse, useExecuteSearch } from "../hooks/use-search";
import { toBackendProtocolColumns, uniqueProtocolIds } from "../lib/protocol-column-id";
import {
  AGGREGATION_LABELS,
  aggregationModeToWire,
  computeScopeForcesSingleRun,
  useAggregationMode,
  wireToAggregationMode,
} from "../lib/use-aggregation-mode";
import type { AggregationMode } from "../lib/use-aggregation-mode";
import {
  type ActivityValue,
  type SavedSearch,
  type SearchQuery,
  type SortDir,
  type SortField,
  anyProtocolActivity,
} from "../types";
import { CompoundComparison } from "./search/compound-comparison";
import { CompoundDetailSheet } from "./search/compound-detail-sheet";
import { QuerySummary, searchQueryKey, structureQuery } from "./search/query-summary";
import { ReportCustomizer } from "./search/report-customizer";
import { ResultsGrid } from "./search/results-grid";
import {
  ResultsSelectionActions,
  ResultsToolbarActions,
  ResultsToolbarLeft,
  ResultsViewControls,
} from "./search/results-toolbar";
import { SaveSearchDialog } from "./search/save-search-dialog";
import { SEARCH_PAGE_SIZE, SearchForm } from "./search/search-form";
import { SearchStructureReference } from "./search/search-structure-reference";

// ─── Types ──────────────────────────────────────────────────────────────────

type EnrichedMolecule = Molecule & { activity?: Record<string, ActivityValue> };

// ─── Search state reducer ───────────────────────────────────────────────────

interface SearchState {
  currentQuery: SearchQuery | null;
  executedAggregation: AggregationMode;
  protocolColumns: string[];
  results: EnrichedMolecule[];
  nextCursor: string | null;
  totalCount: number | null;
  hasSearched: boolean;
  selectedMolecule: EnrichedMolecule | null;
  selectedIndex: number;
  sortBy: SortField | undefined;
  sortDir: SortDir;
  gridSelectedIds: Set<string>;
}

type SearchAction =
  | { type: "reset" }
  | {
      type: "searchStart";
    }
  | {
      type: "searchComplete";
      query: SearchQuery;
      protocolColumns: string[];
      aggregation: AggregationMode;
      results: EnrichedMolecule[];
      nextCursor: string | null;
      totalCount: number | null;
    }
  | {
      type: "loadMoreComplete";
      results: EnrichedMolecule[];
      nextCursor: string | null;
      totalCount: number | null;
    }
  | { type: "setSort"; sortBy: SortField | undefined; sortDir: SortDir }
  | { type: "setGridSelection"; ids: Set<string> }
  | { type: "select"; molecule: EnrichedMolecule; index: number }
  | { type: "navigate"; index: number; molecule: EnrichedMolecule | null }
  | { type: "clearSelection" };

const initialSearchState: SearchState = {
  currentQuery: null,
  executedAggregation: "latest",
  protocolColumns: [],
  results: [],
  nextCursor: null,
  totalCount: null,
  hasSearched: false,
  selectedMolecule: null,
  selectedIndex: 0,
  sortBy: undefined,
  sortDir: "asc",
  gridSelectedIds: new Set(),
};

function searchReducer(state: SearchState, action: SearchAction): SearchState {
  switch (action.type) {
    case "reset":
      return initialSearchState;
    case "searchStart":
      return {
        ...state,
        hasSearched: true,
        selectedMolecule: null,
        gridSelectedIds: new Set(),
      };
    case "searchComplete":
      return {
        ...state,
        currentQuery: action.query,
        protocolColumns: action.protocolColumns,
        executedAggregation: action.aggregation,
        results: action.results,
        nextCursor: action.nextCursor,
        totalCount: action.totalCount,
      };
    case "loadMoreComplete":
      return {
        ...state,
        results: [...state.results, ...action.results],
        nextCursor: action.nextCursor,
        totalCount: action.totalCount ?? state.totalCount,
      };
    case "setSort":
      return { ...state, sortBy: action.sortBy, sortDir: action.sortDir };
    case "setGridSelection":
      return { ...state, gridSelectedIds: action.ids };
    case "select":
      return { ...state, selectedMolecule: action.molecule, selectedIndex: action.index };
    case "navigate":
      return {
        ...state,
        selectedIndex: action.index,
        selectedMolecule: action.molecule,
      };
    case "clearSelection":
      return { ...state, selectedMolecule: null };
    default:
      return state;
  }
}

// ─── Inner component (uses useSearchParams, needs Suspense boundary) ───────

function SearchPageInner() {
  const searchParams = useSearchParams();
  const savedSearchId = searchParams.get("saved");

  // ── Project scoping (independent of search state) ──────────────────────
  const [projectIds, setProjectIds] = useState<string[]>([]);

  // The query the form re-parses into its sections. Only set by loads that
  // come from OUTSIDE the form (saved search, scaffold handoff) — re-parsing
  // the form's own executed query wiped half-filled rows and re-derived the
  // protocol and/or grouping differently, so a second Search ran a
  // different query than the first.
  const [formSeed, setFormSeed] = useState<SearchQuery | undefined>(undefined);

  // ── Dialogs (independent of search state) ─────────────────────────────
  const [reportOpen, setReportOpen] = useState(false);
  const [reportColumns, setReportColumns] = useState<string[] | null>(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [pickerMolIds, setPickerMolIds] = useState<string[]>([]);

  // ── Search state (collapsed into one reducer) ──────────────────────────
  const [
    {
      currentQuery,
      executedAggregation,
      protocolColumns,
      results,
      nextCursor,
      totalCount,
      hasSearched,
      selectedMolecule,
      selectedIndex,
      sortBy,
      sortDir,
      gridSelectedIds,
    },
    dispatch,
  ] = useReducer(searchReducer, initialSearchState);

  // ── Hooks ──────────────────────────────────────────────────────────────
  const searchMutation = useExecuteSearch();
  const { data: protocols } = useProtocols();
  const { data: savedSearches } = useSavedSearches();
  const { data: projects } = useProjects();
  const { data: collections } = useCollections();
  const { data: tags } = useTags();
  const summaryContext = {
    protocols: protocols ?? [],
    projects,
    collections,
    tags: tags?.map((tag) => ({
      id: tag.id,
      name: tag.value ? `${tag.key}: ${tag.value}` : tag.key,
    })),
  };
  const [compareOpen, setCompareOpen] = useState(false);
  const [comparisonIds, setComparisonIds] = useState<string[]>([]);
  const [comparisonEndpoints, setComparisonEndpoints] = useState({ targetId: "", counterId: "" });
  const [filtersCollapsed, setFiltersCollapsed] = useState(false);
  const [searchPending, setSearchPending] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const requestVersion = useRef(0);
  const retrySearch = useRef<(() => void) | null>(null);
  const draftQuery = useRef<SearchQuery | null>(null);
  const onDraftChange = useCallback((query: SearchQuery) => {
    draftQuery.current = query;
  }, []);
  const { config: reportConfig, loadFromSavedSearch } = useReportConfig();
  // URL-synced aggregation mode. The toolbar's <AggregationControl /> owns
  // the writer; the page reads + injects into the request body, and also
  // calls `setMode` on the saved-search load path so the URL chip and the
  // request body stay in lock-step with the persisted rule.
  const { mode: aggregationMode, setMode: setAggregationMode } = useAggregationMode();

  // ── Derived: visible protocol IDs for detail panel ─────────────────────
  // Resolves each protocol-column token to its owning protocol.
  // `parts[1]` is NOT the proto_id on `drc:<rd_id>` (2-segment, post
  // migration 033) — the reverse readout-def index in
  // `uniqueProtocolIds` keeps the detail drawer's "Selected vs Others"
  // split honest for DR-only column sets.
  const visibleProtocolIds = useMemo(
    () => uniqueProtocolIds(protocolColumns, protocols ?? []),
    [protocolColumns, protocols],
  );

  // ── Derived: visible protocol IDs + the selected compound's "any" matches ─
  // The detail sheet needs to show every protocol the selected compound
  // actually matched in an any-protocol search, not just the columns on
  // screen (an any-protocol row has no dedicated protocol column). Derived
  // from `selectedMolecule` (not a click-time snapshot) so prev/next
  // navigation stays correct without a separate state to keep in sync.
  const sheetVisibleProtocolIds = useMemo(
    () => [
      ...new Set([
        ...visibleProtocolIds,
        ...(selectedMolecule
          ? (anyProtocolActivity(selectedMolecule)?.entries.map((e) => e.protocol_id) ?? [])
          : []),
      ]),
    ],
    [visibleProtocolIds, selectedMolecule],
  );

  // ── Derived: should the toolbar Summarize: dropdown be hidden? ──────────
  // True iff every active activity criterion narrows its run scope to one
  // run, in which case every cell deterministically reduces to one value
  // and the dropdown is a no-op. Driven off the *executed* query so the
  // toolbar swap lines up with the cells actually on screen — editing the
  // search form without re-running keeps the previous toolbar state until
  // the next Search.
  const scopeForcesSingleRun = useMemo(
    () => computeScopeForcesSingleRun(currentQuery?.criteria ?? []),
    [currentQuery],
  );

  // ── Enrichment helper ──────────────────────────────────────────────────
  const enrichItems = useCallback(
    (data: EnrichedSearchResponse): EnrichedMolecule[] =>
      data.items.map((mol) => ({
        ...mol,
        activity: data.activity_data?.[mol.id] ?? undefined,
      })),
    [],
  );

  // Commit rows and their query together. Request versions also invalidate
  // responses after Reset or a newer search, including saved-search handoffs.
  const { mutateAsync } = searchMutation;
  const executeRequest = useCallback(
    function run(
      query: SearchQuery,
      columns: string[],
      mode: AggregationMode,
      options: { cursor?: string; collapse?: boolean } = {},
    ) {
      const version = ++requestVersion.current;
      const startingDraft = draftQuery.current ? searchQueryKey(draftQuery.current) : null;
      setSearchPending(true);
      setSearchError(null);
      if (!options.cursor) {
        setCompareOpen(false);
        dispatch({ type: "searchStart" });
      }
      retrySearch.current = () => run(query, columns, mode, options);
      const backendCols = toBackendProtocolColumns(columns);
      void mutateAsync({
        input: {
          query,
          ...(backendCols.length ? { protocol_columns: backendCols } : {}),
          aggregation: aggregationModeToWire(mode),
        },
        limit: SEARCH_PAGE_SIZE,
        cursor: options.cursor,
        sort_by: sortBy,
        sort_dir: sortDir,
      })
        .then((data) => {
          if (version !== requestVersion.current) return;
          const payload = {
            results: enrichItems(data),
            nextCursor: data.next_cursor ?? null,
            totalCount: data.total_count ?? null,
          };
          if (options.cursor) dispatch({ type: "loadMoreComplete", ...payload });
          else
            dispatch({
              type: "searchComplete",
              query,
              protocolColumns: columns,
              aggregation: mode,
              ...payload,
            });
          if (
            options.collapse &&
            (!draftQuery.current ||
              searchQueryKey(draftQuery.current) === searchQueryKey(query) ||
              searchQueryKey(draftQuery.current) === startingDraft)
          )
            setFiltersCollapsed(true);
          retrySearch.current = null;
        })
        .catch((error: unknown) => {
          if (version !== requestVersion.current) return;
          setSearchError(
            error instanceof Error
              ? error.message.replace(/^API error: \d+ — /, "")
              : "The search could not be completed.",
          );
        })
        .finally(() => {
          if (version === requestVersion.current) setSearchPending(false);
        });
    },
    [mutateAsync, sortBy, sortDir, enrichItems],
  );

  const handleSearch = useCallback(
    (query: SearchQuery, columns: string[]) => {
      executeRequest(query, columns, aggregationMode, { collapse: true });
    },
    [executeRequest, aggregationMode],
  );

  const handleLoadMore = useCallback(() => {
    if (currentQuery && nextCursor)
      executeRequest(currentQuery, protocolColumns, executedAggregation, { cursor: nextCursor });
  }, [currentQuery, nextCursor, protocolColumns, executedAggregation, executeRequest]);

  const handleUpdateReport = useCallback(() => {
    if (currentQuery)
      executeRequest(currentQuery, reportColumns ?? protocolColumns, aggregationMode);
    setReportOpen(false);
  }, [currentQuery, protocolColumns, reportColumns, aggregationMode, executeRequest]);

  const handleSetProtocolColumns = useCallback((next: string[]) => {
    setReportColumns(next);
  }, []);

  const previousAggregationModeRef = useRef(aggregationMode);
  useEffect(() => {
    if (previousAggregationModeRef.current === aggregationMode) return;
    previousAggregationModeRef.current = aggregationMode;
    if (currentQuery) executeRequest(currentQuery, protocolColumns, aggregationMode);
  }, [aggregationMode, currentQuery, protocolColumns, executeRequest]);

  // ── Auto-fire handoffs (saved search + scaffold) ──────────────────────
  //
  // Both handoffs follow a TWO-EFFECT pattern: "prepare" sets pending state,
  // then "fire" reacts to that state and runs the mutation. This is more
  // robust than the previous mount-time single-effect approach, which had
  // a recurring soft-navigation bug — the mutation call would fire (no
  // visible error) but the request never reached the network. Splitting
  // into prepare + fire lets React commit the prep state, then fire the
  // mutation from a clean re-render cycle. The mutation goes through
  // `handleSearch` (the same path the chemist's Search button uses) so
  // the deps are always fresh.
  type PendingSavedSearchLoad = {
    query: SearchQuery;
    aggregationMode: AggregationMode;
    protocolColumns: string[];
    columnsBlob: Record<string, unknown> | null;
  };

  const [pendingSavedSearchLoad, setPendingSavedSearchLoad] =
    useState<PendingSavedSearchLoad | null>(null);
  const [loadedSavedSearchId, setLoadedSavedSearchId] = useState<string | null>(null);
  const [pendingScaffoldQuery, setPendingScaffoldQuery] = useState<SearchQuery | null>(null);

  // PREPARE: saved-search load — when the URL has ?saved=<id> and the
  // savedSearches list has resolved, decode the saved query + columns and
  // stage them for the fire effect to execute. Skip if we already loaded
  // this id in the current mount (idempotent across re-renders driven by
  // other state churn).
  useEffect(() => {
    if (!savedSearchId || !savedSearches) return;
    if (loadedSavedSearchId === savedSearchId) return;
    if (pendingSavedSearchLoad) return; // already staged, wait for fire

    const saved = savedSearches.find((s: SavedSearch) => s.id === savedSearchId);
    if (!saved) return;

    const rawQuery = saved.query as Record<string, unknown>;
    // The aggregation rule is co-located inside the saved `query` blob
    // (Task 14). Old saved searches (pre-Task 14) won't have this key
    // and fall back to "latest" — matching the FE default.
    const savedAggregation = rawQuery?.aggregation;
    const nextAggregationMode =
      typeof savedAggregation === "string" ? wireToAggregationMode(savedAggregation) : "latest";
    // Strip the aggregation field out before handing the query to the BE
    // — the search query schema doesn't include it as a criterion (it
    // travels as a top-level `input.aggregation` instead).
    const { aggregation: _aggregation, ...queryWithoutAggregation } = rawQuery;
    const query = queryWithoutAggregation as unknown as SearchQuery;
    if (!query?.criteria) return;

    const cols = saved.columns as { protocolColumns?: string[] } | null;
    const restoredColumns = cols?.protocolColumns ?? [];

    setPendingSavedSearchLoad({
      query,
      aggregationMode: nextAggregationMode,
      protocolColumns: restoredColumns,
      columnsBlob: saved.columns as Record<string, unknown> | null,
    });
  }, [savedSearchId, savedSearches, loadedSavedSearchId, pendingSavedSearchLoad]);

  // FIRE: saved-search load — execute the staged search. Uses executeRequest
  // directly because saved searches carry their OWN
  // aggregationMode + columns that differ from the page's current state.
  useEffect(() => {
    if (!pendingSavedSearchLoad) return;
    const {
      query,
      aggregationMode: aggMode,
      protocolColumns: restoredColumns,
      columnsBlob,
    } = pendingSavedSearchLoad;

    // Clear pending + mark loaded BEFORE async work so a re-render from
    // setAggregationMode below doesn't bounce the prep effect into firing
    // a second time.
    setPendingSavedSearchLoad(null);
    setLoadedSavedSearchId(savedSearchId);

    loadFromSavedSearch(columnsBlob);
    // Pin the ref before flipping the URL so the aggregation auto-refire
    // effect doesn't double-fire on the next render.
    previousAggregationModeRef.current = aggMode;
    setAggregationMode(aggMode);

    setFormSeed(query);
    executeRequest(query, restoredColumns, aggMode, { collapse: true });
  }, [
    pendingSavedSearchLoad,
    savedSearchId,
    executeRequest,
    loadFromSavedSearch,
    setAggregationMode,
  ]);

  // PREPARE: scaffold handoff — consume the sessionStorage stash (one-shot
  // via the helper's removeItem on read). Saved-search takes priority; if
  // ?saved= is set, discard the stash so it doesn't bleed into a later
  // visit without ?saved=.
  useEffect(() => {
    if (savedSearchId) {
      consumeScaffoldSearch();
      return;
    }
    const criterion = consumeScaffoldSearch();
    if (!criterion) return;
    setPendingScaffoldQuery({ logic: "and", criteria: [criterion] });
  }, [savedSearchId]);

  // FIRE: scaffold handoff — route through handleSearch (the canonical
  // path the Search button uses). handleSearch's deps are tracked by its
  // useCallback so we always get an up-to-date reference, avoiding the
  // stale-closure bug where the inline mutation call would fire but the
  // request never reached the network.
  useEffect(() => {
    if (!pendingScaffoldQuery) return;
    const query = pendingScaffoldQuery;
    setPendingScaffoldQuery(null);
    setFormSeed(query);
    handleSearch(query, []);
  }, [pendingScaffoldQuery, handleSearch]);

  // ── Export request builder ─────────────────────────────────────────────
  // Produces a fully-parameterised ExportRequest closure for the shared
  // ExportToolbar. Returns null if no search has been run yet (the toolbar
  // disables the button in that case).
  const buildExportRequest = useCallback(
    (format: ExportFormat): ExportRequest | null => {
      if (!currentQuery) return null;
      const backendCols = toBackendProtocolColumns(protocolColumns);
      return {
        source: "search",
        format,
        filename_hint: `cellar-search-${new Date().toISOString().slice(0, 10)}`,
        payload: {
          query: currentQuery,
          ...(backendCols.length ? { protocol_columns: backendCols } : {}),
          aggregation: aggregationModeToWire(executedAggregation),
          // Project scope already rides in `query` as a project criterion —
          // the export runs exactly the grid's search.
          sort_by: sortBy,
          sort_dir: sortDir,
          // Mirror the chemist's on-screen grid: structure visibility,
          // property column whitelist, image size. The BE column builder
          // reads this and trims columns / sizes images accordingly.
          reportConfig,
        },
      };
    },
    [currentQuery, protocolColumns, executedAggregation, sortBy, sortDir, reportConfig],
  );

  // ── Add to collection ──────────────────────────────────────────────────
  const handleAddToCollection = useCallback(() => {
    if (gridSelectedIds.size === 0) return;
    setPickerMolIds(Array.from(gridSelectedIds));
  }, [gridSelectedIds]);

  // ── Row click -> detail panel ──────────────────────────────────────────
  const handleRowClick = useCallback(
    (molecule: EnrichedMolecule) => {
      const idx = results.findIndex((m) => m.id === molecule.id);
      dispatch({ type: "select", molecule, index: idx >= 0 ? idx : 0 });
    },
    [results],
  );

  // ── Detail panel navigation ────────────────────────────────────────────
  const handleDetailNavigate = useCallback(
    (direction: "prev" | "next") => {
      const nextIdx =
        direction === "prev"
          ? Math.max(0, selectedIndex - 1)
          : Math.min(results.length - 1, selectedIndex + 1);
      dispatch({ type: "navigate", index: nextIdx, molecule: results[nextIdx] ?? null });
    },
    [selectedIndex, results],
  );

  // ─── Layout ────────────────────────────────────────────────────────────

  return (
    <div className="compound-search-page">
      {/* Let the viewport own scrolling so the search action bar can stay sticky. */}
      <style>{"main:has(> .compound-search-page) { overflow: visible; }"}</style>
      <div className="space-y-2">
        {/* Search form — always visible */}
        <SearchForm
          initialQuery={formSeed}
          projectIds={projectIds}
          onProjectsChange={setProjectIds}
          onSearch={handleSearch}
          onReset={() => {
            requestVersion.current++;
            retrySearch.current = null;
            setSearchPending(false);
            setSearchError(null);
            setFiltersCollapsed(false);
            setCompareOpen(false);
            dispatch({ type: "reset" });
          }}
          isLoading={searchPending}
          executedQuery={currentQuery}
          collapsed={filtersCollapsed}
          onCollapsedChange={setFiltersCollapsed}
          onDraftChange={onDraftChange}
          summaryContext={summaryContext}
          protocols={protocols ?? []}
        />

        {searchError && (
          <div
            role="alert"
            className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <div className="min-w-0 flex-1 text-sm">
              <p className="font-medium">Search could not be completed</p>
              <p className="mt-1 break-words text-muted-foreground">{searchError}</p>
              {currentQuery && (
                <p className="mt-1 text-muted-foreground">
                  The previous results are still shown below.
                </p>
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={searchPending}
              onClick={() => retrySearch.current?.()}
            >
              Retry
            </Button>
          </div>
        )}
        {searchPending && (
          <output className="flex items-center gap-2 rounded-lg border bg-muted/40 px-4 py-3 text-sm">
            <Loader2 className="h-4 w-4 animate-spin" />
            {currentQuery
              ? "Updating results… Previous results remain visible until the search completes."
              : "Searching compounds…"}
          </output>
        )}
        {hasSearched && (currentQuery || searchPending) && (
          <ResultsGrid
            results={results}
            protocolColumns={protocolColumns}
            protocols={protocols ?? []}
            reportConfig={reportConfig}
            loading={searchPending && !currentQuery}
            structureCriterion={structureQuery(currentQuery)}
            aggregationMode={executedAggregation}
            onRowClick={handleRowClick}
            selectedIds={gridSelectedIds}
            toolbarLeft={
              <ResultsToolbarLeft resultCount={totalCount} selectedCount={gridSelectedIds.size} />
            }
            summary={
              currentQuery && (
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <QuerySummary
                      query={currentQuery}
                      context={summaryContext}
                      className="text-xs leading-relaxed text-foreground/70"
                    />
                    {protocolColumns.length > 0 && (
                      <span className="shrink-0 rounded-full border border-primary/15 bg-primary/5 px-2 py-0.5 text-[11px] text-primary">
                        {scopeForcesSingleRun
                          ? "Single run per compound"
                          : AGGREGATION_LABELS[executedAggregation]}
                      </span>
                    )}
                  </div>
                  <SearchStructureReference criterion={structureQuery(currentQuery)} />
                </div>
              )
            }
            toolbarActions={
              <ResultsToolbarActions onSaveSearch={() => setSaveOpen(true)} busy={searchPending} />
            }
            viewControls={
              <ResultsViewControls
                onCustomizeReport={() => {
                  setReportColumns(protocolColumns);
                  setReportOpen(true);
                }}
                scopeForcesSingleRun={scopeForcesSingleRun}
                busy={searchPending}
                hasAssays={protocolColumns.length > 0}
                hasCurves={protocolColumns.some((column) => column.startsWith("drc:"))}
              />
            }
            selectionActions={
              <ResultsSelectionActions
                selectedCount={gridSelectedIds.size}
                onAddToCollection={handleAddToCollection}
                onCompare={() => {
                  setComparisonIds(Array.from(gridSelectedIds));
                  setCompareOpen(true);
                }}
                onClearSelection={() => dispatch({ type: "setGridSelection", ids: new Set() })}
                busy={searchPending}
              />
            }
            onSelectionChange={(ids) => dispatch({ type: "setGridSelection", ids })}
            buildExportRequest={searchPending ? undefined : buildExportRequest}
            footer={
              nextCursor && (
                <div className="flex justify-center py-3">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleLoadMore}
                    disabled={searchPending}
                  >
                    {searchPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                    Load More
                  </Button>
                </div>
              )
            }
          />
        )}

        {!hasSearched && (
          <div className="flex items-center justify-center py-20 text-sm text-muted-foreground">
            {/* Action-focused copy. The forecast count lives next to the
                Search button now, so this prompt no longer contradicts it. */}
            Press Search or ⌘↵ to load results.
          </div>
        )}
      </div>

      {/* Overlays */}
      {compareOpen && (
        <CompoundComparison
          molecules={comparisonIds.flatMap((id) => {
            const mol = results.find((row) => row.id === id);
            return mol ? [mol] : [];
          })}
          availableMolecules={results}
          onMoleculesChange={setComparisonIds}
          endpointPair={comparisonEndpoints}
          onEndpointPairChange={setComparisonEndpoints}
          onSaveShortlist={() => setPickerMolIds(comparisonIds)}
          open={pickerMolIds.length === 0}
          onLoadMore={nextCursor ? handleLoadMore : undefined}
          loading={searchPending}
          protocols={protocols ?? []}
          protocolColumns={protocolColumns}
          mode={executedAggregation}
          onClose={() => setCompareOpen(false)}
        />
      )}
      <CompoundDetailSheet
        key={selectedMolecule?.id ?? "closed"}
        protocolColumns={protocolColumns}
        protocols={protocols ?? []}
        molecule={selectedMolecule}
        visibleProtocolIds={sheetVisibleProtocolIds}
        currentIndex={selectedIndex}
        totalCount={results.length}
        onNavigate={handleDetailNavigate}
        onOpenChange={(open) => !open && dispatch({ type: "clearSelection" })}
        currentQuery={currentQuery}
        aggregationMode={executedAggregation}
      />

      <ReportCustomizer
        open={reportOpen}
        onOpenChange={setReportOpen}
        onUpdate={handleUpdateReport}
        protocols={protocols ?? []}
        activeProtocolIds={visibleProtocolIds}
        protocolColumns={reportColumns ?? protocolColumns}
        onProtocolColumnsChange={handleSetProtocolColumns}
      />

      {currentQuery && (
        <SaveSearchDialog
          open={saveOpen}
          onOpenChange={setSaveOpen}
          query={currentQuery}
          protocolColumns={protocolColumns}
          reportConfig={reportConfig}
          executedAggregation={executedAggregation}
        />
      )}

      <CollectionPickerDialog
        open={pickerMolIds.length > 0}
        onOpenChange={(open) => {
          if (!open) setPickerMolIds([]);
        }}
        moleculeIds={pickerMolIds}
        onComplete={() => setPickerMolIds([])}
      />
    </div>
  );
}

// ─── Exported wrapper with Suspense (required for useSearchParams) ─────────

export function SearchPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-[calc(100vh-64px)] items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      }
    >
      <CompoundCurvesProvider>
        <SearchPageInner />
      </CompoundCurvesProvider>
    </Suspense>
  );
}
