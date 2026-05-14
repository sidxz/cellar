"use client";

import { Suspense, useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import type { Molecule } from "@/features/chemical-registration/types";
import { useProtocols } from "@/features/screening-assay/hooks/use-protocols";
import { useSdfExport } from "@/features/chemical-registration/hooks/use-sdf-export";
import type { SearchQuery, ActivityValue, SortField, SortDir, SavedSearch } from "../types";
import { useExecuteSearch, type EnrichedSearchResponse } from "../hooks/use-search";
import { useSavedSearches } from "../hooks/use-saved-searches";
import { useReportConfig } from "../hooks/use-report-config";
import { uniqueProtocolIds } from "../lib/protocol-column-id";
import { SearchForm } from "./search/search-form";
import { ResultsToolbar } from "./search/results-toolbar";
import { ResultsGrid } from "./search/results-grid";
import { CompoundDetailSheet } from "./search/compound-detail-sheet";
import { ReportCustomizer } from "./search/report-customizer";
import { SaveSearchDialog } from "./search/save-search-dialog";
import { CollectionPickerDialog } from "@/shared/components/collection-picker-dialog";

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
  const { exportSdf } = useSdfExport();

  // ── Derive extra rd: columns from report config readout selections ────
  const readoutExtraColumns = useMemo(() => {
    const cols: string[] = [];
    for (const [protoId, rdIds] of Object.entries(reportConfig.visibleFields.readoutColumns)) {
      for (const rdId of rdIds) {
        cols.push(`rd:${protoId}:${rdId}`);
      }
    }
    return cols;
  }, [reportConfig.visibleFields.readoutColumns]);

  // ── Merged protocol columns (search-derived + report config readouts) ──
  const mergedProtocolColumns = useMemo(() => {
    const set = new Set([...protocolColumns, ...readoutExtraColumns]);
    return [...set];
  }, [protocolColumns, readoutExtraColumns]);

  // ── Derived: visible protocol IDs for detail panel ─────────────────────
  // Resolves each protocol-column token to its owning protocol.
  // `parts[1]` is NOT the proto_id on `drc:<rd_id>` (2-segment, post
  // migration 033) — the reverse readout-def index in
  // `uniqueProtocolIds` keeps the detail drawer's "Selected vs Others"
  // split honest for DR-only column sets.
  const visibleProtocolIds = useMemo(
    () => uniqueProtocolIds(mergedProtocolColumns, protocols ?? []),
    [mergedProtocolColumns, protocols],
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

      // Merge search-derived columns with report config readout selections
      const allColumns = [...new Set([...columns, ...readoutExtraColumns])];
      const input = {
        query,
        ...(allColumns.length > 0 ? { protocol_columns: allColumns } : {}),
      };

      searchMutation.mutate(
        { input, limit: SEARCH_PAGE_SIZE, sort_by: sortBy, sort_dir: sortDir },
        {
          onSuccess: (data) => {
            dispatch({
              type: "searchComplete",
              results: enrichItems(data),
              nextCursor: data.next_cursor,
              totalCount: data.total_count,
            });
          },
          onError: (err) => {
            console.error("[Search] mutation failed:", err);
            dispatch({ type: "searchComplete", results: [], nextCursor: null, totalCount: null });
          },
        },
      );
    },
    [searchMutation, sortBy, sortDir, enrichItems, readoutExtraColumns],
  );

  // ── handleLoadMore ─────────────────────────────────────────────────────
  const handleLoadMore = useCallback(() => {
    if (!currentQuery || !nextCursor) return;
    const input = {
      query: currentQuery,
      ...(mergedProtocolColumns.length > 0 ? { protocol_columns: mergedProtocolColumns } : {}),
    };

    searchMutation.mutate(
      { input, cursor: nextCursor, limit: SEARCH_PAGE_SIZE, sort_by: sortBy, sort_dir: sortDir },
      {
        onSuccess: (data) => {
          dispatch({
            type: "loadMoreComplete",
            results: enrichItems(data),
            nextCursor: data.next_cursor,
            totalCount: data.total_count,
          });
        },
      },
    );
  }, [currentQuery, nextCursor, searchMutation, mergedProtocolColumns, sortBy, sortDir, enrichItems]);

  // ── Re-fetch with current merged columns (called from report customizer) ─
  const handleUpdateReport = useCallback(() => {
    if (!currentQuery || !hasSearched) return;
    const allColumns = [...new Set([...protocolColumns, ...readoutExtraColumns])];
    const input = {
      query: currentQuery,
      ...(allColumns.length > 0 ? { protocol_columns: allColumns } : {}),
    };
    searchMutation.mutate(
      { input, limit: SEARCH_PAGE_SIZE, sort_by: sortBy, sort_dir: sortDir },
      {
        onSuccess: (data) => {
          dispatch({
            type: "searchComplete",
            results: enrichItems(data),
            nextCursor: data.next_cursor,
            totalCount: data.total_count,
          });
        },
      },
    );
    setReportOpen(false);
  }, [currentQuery, hasSearched, protocolColumns, readoutExtraColumns, searchMutation, sortBy, sortDir, enrichItems]);

  // ── Load saved search from URL ─────────────────────────────────────────
  const savedSearchLoadedRef = useRef<string | null>(null);
  const { mutate: runSearch } = searchMutation;

  useEffect(() => {
    if (!savedSearchId || !savedSearches) return;
    if (savedSearchLoadedRef.current === savedSearchId) return;
    savedSearchLoadedRef.current = savedSearchId;

    const saved = savedSearches.find((s: SavedSearch) => s.id === savedSearchId);
    if (!saved) return;

    loadFromSavedSearch(saved.columns);

    const cols = saved.columns as { protocolColumns?: string[] } | null;
    const restoredColumns = cols?.protocolColumns ?? [];
    const query = saved.query as unknown as SearchQuery;
    if (!query?.criteria) return;

    // Inline the search instead of going through handleSearch — its closure
    // captures readoutExtraColumns from a render that loadFromSavedSearch
    // above is about to invalidate, which can lose the mutation's onSuccess.
    dispatch({ type: "searchStart", query, protocolColumns: restoredColumns });

    const input = {
      query,
      ...(restoredColumns.length > 0 ? { protocol_columns: restoredColumns } : {}),
    };

    runSearch(
      { input, limit: SEARCH_PAGE_SIZE },
      {
        onSuccess: (data) => {
          dispatch({
            type: "searchComplete",
            results: enrichItems(data),
            nextCursor: data.next_cursor,
            totalCount: data.total_count,
          });
        },
        onError: (err) => {
          console.error("[Search] saved-search mutation failed:", err);
          dispatch({ type: "searchComplete", results: [], nextCursor: null, totalCount: null });
        },
      },
    );
  }, [savedSearchId, savedSearches, loadFromSavedSearch, runSearch, enrichItems]);

  // ── SDF export ─────────────────────────────────────────────────────────
  const handleExportSdf = useCallback(() => {
    if (!results.length) return;
    const ids = gridSelectedIds.size > 0
      ? Array.from(gridSelectedIds)
      : results.map((m) => m.id);
    exportSdf(ids, "search-results.sdf");
  }, [results, gridSelectedIds, exportSdf]);

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

        {/* Results area */}
        {hasSearched && (
          <>
            <ResultsToolbar
              resultCount={totalCount}
              selectedCount={gridSelectedIds.size}
              onSelectAll={handleSelectAll}
              onSelectNone={handleSelectNone}
              onExport={handleExportSdf}
              onAddToCollection={handleAddToCollection}
              onCustomizeReport={() => setReportOpen(true)}
              onSaveSearch={() => setSaveOpen(true)}
            />
            <ResultsGrid
              results={results}
              protocolColumns={mergedProtocolColumns}
              protocols={protocols ?? []}
              reportConfig={reportConfig}
              loading={searchMutation.isPending && results.length === 0}
              onRowClick={handleRowClick}
              selectedIds={gridSelectedIds}
              onSelectionChange={(ids) => dispatch({ type: "setGridSelection", ids })}
            />
            {nextCursor && (
              <div className="flex justify-center py-3">
                <Button variant="outline" size="sm" onClick={handleLoadMore} disabled={searchMutation.isPending}>
                  {searchMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
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
        onClose={() => dispatch({ type: "clearSelection" })}
      />

      <ReportCustomizer
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        onUpdate={handleUpdateReport}
        protocols={protocols ?? []}
        activeProtocolIds={visibleProtocolIds}
      />

      {currentQuery && (
        <SaveSearchDialog
          open={saveOpen}
          onClose={() => setSaveOpen(false)}
          query={currentQuery}
          protocolColumns={mergedProtocolColumns}
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
