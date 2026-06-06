"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { consumeScaffoldSearch } from "@/features/research-organization/lib/scaffold-search-handoff";
import { useProtocols } from "@/features/screening-assay/hooks/use-protocols";
import { CollectionPickerDialog } from "@/shared/components/collection-picker-dialog";
import type { ExportFormat, ExportRequest } from "@/shared/components/export/types";
import { Button } from "@/shared/components/ui/button";
import { Loader2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { useReportConfig } from "../hooks/use-report-config";
import { useSavedSearches } from "../hooks/use-saved-searches";
import { type EnrichedSearchResponse, useExecuteSearch } from "../hooks/use-search";
import { toBackendProtocolColumns, uniqueProtocolIds } from "../lib/protocol-column-id";
import {
  aggregationModeToWire,
  computeScopeForcesSingleRun,
  useAggregationMode,
  wireToAggregationMode,
} from "../lib/use-aggregation-mode";
import type { AggregationMode } from "../lib/use-aggregation-mode";
import type { ActivityValue, SavedSearch, SearchQuery, SortDir, SortField } from "../types";
import { CompoundDetailSheet } from "./search/compound-detail-sheet";
import { ReportCustomizer } from "./search/report-customizer";
import { ResultsGrid } from "./search/results-grid";
import { ResultsToolbarActions, ResultsToolbarLeft } from "./search/results-toolbar";
import { SaveSearchDialog } from "./search/save-search-dialog";
import { SearchForm } from "./search/search-form";

// ─── Types ──────────────────────────────────────────────────────────────────

type EnrichedMolecule = Molecule & { activity?: Record<string, ActivityValue> };

/** Server-side page size for compound search results. Driven by what the
 * AG Grid viewport can comfortably render before the user scrolls; keep in
 * sync with the cursor pagination contract on the backend. */
const SEARCH_PAGE_SIZE = 100;

// ─── Search state reducer ───────────────────────────────────────────────────

interface SearchState {
  currentQuery: SearchQuery | null;
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
      query: SearchQuery;
      protocolColumns: string[];
    }
  | {
      type: "searchComplete";
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
  | { type: "setProtocolColumns"; protocolColumns: string[] }
  | { type: "setSort"; sortBy: SortField | undefined; sortDir: SortDir }
  | { type: "setGridSelection"; ids: Set<string> }
  | { type: "select"; molecule: EnrichedMolecule; index: number }
  | { type: "navigate"; index: number; molecule: EnrichedMolecule | null }
  | { type: "clearSelection" };

const initialSearchState: SearchState = {
  currentQuery: null,
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
        currentQuery: action.query,
        protocolColumns: action.protocolColumns,
        hasSearched: true,
        selectedMolecule: null,
        gridSelectedIds: new Set(),
      };
    case "searchComplete":
      return {
        ...state,
        results: action.results,
        nextCursor: action.nextCursor,
        totalCount: action.totalCount,
      };
    case "loadMoreComplete":
      return {
        ...state,
        results: [...state.results, ...action.results],
        nextCursor: action.nextCursor,
        totalCount: action.totalCount,
      };
    case "setProtocolColumns":
      // Customizer-driven update to which columns the grid renders. The
      // customizer reads its check-state from `state.protocolColumns`, so
      // this is the single SoT — no separate `readoutColumns` shadow state.
      return { ...state, protocolColumns: action.protocolColumns };
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

  // ── Dialogs (independent of search state) ─────────────────────────────
  const [reportOpen, setReportOpen] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [pickerMolIds, setPickerMolIds] = useState<string[]>([]);

  // ── Search state (collapsed into one reducer) ──────────────────────────
  const [
    {
      currentQuery,
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

  // ── handleSearch ───────────────────────────────────────────────────────
  const handleSearch = useCallback(
    (query: SearchQuery, columns: string[]) => {
      dispatch({ type: "searchStart", query, protocolColumns: columns });

      // BE only understands the canonical `drc:<rd>` / `rd:<proto>:<rd>`
      // shapes. Narrowed `drc:<rd>:kind:level` tokens (introduced by the
      // customizer for per-intercept visibility) collapse to their parent
      // here so the activity-service doesn't crash trying to parse a
      // 4-segment drc token as a UUID.
      const backendCols = toBackendProtocolColumns(columns);
      const input = {
        query,
        ...(backendCols.length > 0 ? { protocol_columns: backendCols } : {}),
        aggregation: aggregationModeToWire(aggregationMode),
      };

      searchMutation.mutate(
        { input, limit: SEARCH_PAGE_SIZE, sort_by: sortBy, sort_dir: sortDir },
        {
          onSuccess: (data) => {
            dispatch({
              type: "searchComplete",
              results: enrichItems(data),
              nextCursor: data.next_cursor ?? null,
              totalCount: data.total_count ?? null,
            });
          },
          onError: (err) => {
            console.error("[Search] mutation failed:", err);
            dispatch({ type: "searchComplete", results: [], nextCursor: null, totalCount: null });
          },
        },
      );
    },
    [searchMutation, sortBy, sortDir, enrichItems, aggregationMode],
  );

  // ── handleLoadMore ─────────────────────────────────────────────────────
  const handleLoadMore = useCallback(() => {
    if (!currentQuery || !nextCursor) return;
    const backendCols = toBackendProtocolColumns(protocolColumns);
    const input = {
      query: currentQuery,
      ...(backendCols.length > 0 ? { protocol_columns: backendCols } : {}),
      aggregation: aggregationModeToWire(aggregationMode),
    };

    searchMutation.mutate(
      { input, cursor: nextCursor, limit: SEARCH_PAGE_SIZE, sort_by: sortBy, sort_dir: sortDir },
      {
        onSuccess: (data) => {
          dispatch({
            type: "loadMoreComplete",
            results: enrichItems(data),
            nextCursor: data.next_cursor ?? null,
            totalCount: data.total_count ?? null,
          });
        },
      },
    );
  }, [
    currentQuery,
    nextCursor,
    searchMutation,
    protocolColumns,
    sortBy,
    sortDir,
    enrichItems,
    aggregationMode,
  ]);

  // ── Re-fetch with current columns (called from report customizer +
  // when the aggregation mode changes) ──────────────────────────────────
  const handleUpdateReport = useCallback(() => {
    if (!currentQuery || !hasSearched) return;
    const backendCols = toBackendProtocolColumns(protocolColumns);
    const input = {
      query: currentQuery,
      ...(backendCols.length > 0 ? { protocol_columns: backendCols } : {}),
      aggregation: aggregationModeToWire(aggregationMode),
    };
    searchMutation.mutate(
      { input, limit: SEARCH_PAGE_SIZE, sort_by: sortBy, sort_dir: sortDir },
      {
        onSuccess: (data) => {
          dispatch({
            type: "searchComplete",
            results: enrichItems(data),
            nextCursor: data.next_cursor ?? null,
            totalCount: data.total_count ?? null,
          });
        },
      },
    );
    setReportOpen(false);
  }, [
    currentQuery,
    hasSearched,
    protocolColumns,
    searchMutation,
    sortBy,
    sortDir,
    enrichItems,
    aggregationMode,
  ]);

  const handleSetProtocolColumns = useCallback((next: string[]) => {
    dispatch({ type: "setProtocolColumns", protocolColumns: next });
  }, []);

  // ── Re-trigger search when aggregation mode changes ────────────────────
  // Mode change is BE-driven (the selection rule lives in the request
  // body), so flipping `?agg=` must re-fetch with the new rule. Skips
  // the very first render so we don't double-fire on initial mount.
  const previousAggregationModeRef = useRef(aggregationMode);
  useEffect(() => {
    if (previousAggregationModeRef.current === aggregationMode) return;
    previousAggregationModeRef.current = aggregationMode;
    if (!currentQuery || !hasSearched) return;

    const backendCols = toBackendProtocolColumns(protocolColumns);
    const input = {
      query: currentQuery,
      ...(backendCols.length > 0 ? { protocol_columns: backendCols } : {}),
      aggregation: aggregationModeToWire(aggregationMode),
    };
    searchMutation.mutate(
      { input, limit: SEARCH_PAGE_SIZE, sort_by: sortBy, sort_dir: sortDir },
      {
        onSuccess: (data) => {
          dispatch({
            type: "searchComplete",
            results: enrichItems(data),
            nextCursor: data.next_cursor ?? null,
            totalCount: data.total_count ?? null,
          });
        },
      },
    );
  }, [
    aggregationMode,
    currentQuery,
    hasSearched,
    protocolColumns,
    searchMutation,
    sortBy,
    sortDir,
    enrichItems,
  ]);

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
  const { mutate: runSearch } = searchMutation;

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

  // FIRE: saved-search load — execute the staged search. Uses runSearch
  // directly (not handleSearch) because saved searches carry their OWN
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

    dispatch({ type: "searchStart", query, protocolColumns: restoredColumns });

    const backendCols = toBackendProtocolColumns(restoredColumns);
    const input = {
      query,
      ...(backendCols.length > 0 ? { protocol_columns: backendCols } : {}),
      aggregation: aggregationModeToWire(aggMode),
    };
    runSearch(
      { input, limit: SEARCH_PAGE_SIZE },
      {
        onSuccess: (data) => {
          dispatch({
            type: "searchComplete",
            results: enrichItems(data),
            nextCursor: data.next_cursor ?? null,
            totalCount: data.total_count ?? null,
          });
        },
        onError: (err) => {
          console.error("[Search] saved-search mutation failed:", err);
          dispatch({
            type: "searchComplete",
            results: [],
            nextCursor: null,
            totalCount: null,
          });
        },
      },
    );
  }, [
    pendingSavedSearchLoad,
    savedSearchId,
    runSearch,
    enrichItems,
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
          aggregation: aggregationModeToWire(aggregationMode),
          ...(projectIds.length ? { project_ids: projectIds } : {}),
          sort_by: sortBy,
          sort_dir: sortDir,
          // Mirror the chemist's on-screen grid: structure visibility,
          // property column whitelist, image size. The BE column builder
          // reads this and trims columns / sizes images accordingly.
          reportConfig: {
            detailLevel: reportConfig.detailLevel,
            plotScale: reportConfig.plotScale,
            showPlotLegend: reportConfig.showPlotLegend,
            imageSize: reportConfig.imageSize,
            columnWidth: reportConfig.columnWidth,
            visibleFields: reportConfig.visibleFields,
          },
        },
      };
    },
    [currentQuery, protocolColumns, aggregationMode, projectIds, sortBy, sortDir, reportConfig],
  );

  // ── Add to collection ──────────────────────────────────────────────────
  const handleAddToCollection = useCallback(() => {
    if (gridSelectedIds.size === 0) return;
    setPickerMolIds(Array.from(gridSelectedIds));
  }, [gridSelectedIds]);

  // ── Select all / none ──────────────────────────────────────────────────
  const handleSelectAll = useCallback(() => {
    dispatch({ type: "setGridSelection", ids: new Set(results.map((m) => m.id)) });
  }, [results]);

  const handleSelectNone = useCallback(() => {
    dispatch({ type: "setGridSelection", ids: new Set() });
  }, []);

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
    <div>
      <div className="space-y-2">
        {/* Search form — always visible */}
        <SearchForm
          initialQuery={currentQuery ?? undefined}
          projectIds={projectIds}
          onProjectsChange={setProjectIds}
          onSearch={handleSearch}
          isLoading={searchMutation.isPending}
          protocols={protocols ?? []}
        />

        {/* Results area. The toolbar (result count, select, action buttons,
            Export) lives inline on the grid's own toolbar row so the page
            doesn't burn an extra row for Export. */}
        {hasSearched && (
          <>
            <ResultsGrid
              results={results}
              protocolColumns={protocolColumns}
              protocols={protocols ?? []}
              reportConfig={reportConfig}
              loading={searchMutation.isPending && results.length === 0}
              onRowClick={handleRowClick}
              selectedIds={gridSelectedIds}
              toolbarLeft={
                <ResultsToolbarLeft
                  resultCount={totalCount}
                  selectedCount={gridSelectedIds.size}
                  onSelectAll={handleSelectAll}
                  onSelectNone={handleSelectNone}
                />
              }
              toolbarActions={
                <ResultsToolbarActions
                  selectedCount={gridSelectedIds.size}
                  onAddToCollection={handleAddToCollection}
                  onCustomizeReport={() => setReportOpen(true)}
                  onSaveSearch={() => setSaveOpen(true)}
                  scopeForcesSingleRun={scopeForcesSingleRun}
                />
              }
              onSelectionChange={(ids) => dispatch({ type: "setGridSelection", ids })}
              buildExportRequest={buildExportRequest}
            />
            {nextCursor && (
              <div className="flex justify-center py-3">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleLoadMore}
                  disabled={searchMutation.isPending}
                >
                  {searchMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : null}
                  Load More
                </Button>
              </div>
            )}
          </>
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
      <CompoundDetailSheet
        molecule={selectedMolecule}
        visibleProtocolIds={visibleProtocolIds}
        currentIndex={selectedIndex}
        totalCount={results.length}
        onNavigate={handleDetailNavigate}
        onOpenChange={(open) => !open && dispatch({ type: "clearSelection" })}
        currentQuery={currentQuery}
      />

      <ReportCustomizer
        open={reportOpen}
        onOpenChange={setReportOpen}
        onUpdate={handleUpdateReport}
        protocols={protocols ?? []}
        activeProtocolIds={visibleProtocolIds}
        protocolColumns={protocolColumns}
        onProtocolColumnsChange={handleSetProtocolColumns}
      />

      {currentQuery && (
        <SaveSearchDialog
          open={saveOpen}
          onOpenChange={setSaveOpen}
          query={currentQuery}
          protocolColumns={protocolColumns}
          reportConfig={reportConfig}
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
      <SearchPageInner />
    </Suspense>
  );
}
