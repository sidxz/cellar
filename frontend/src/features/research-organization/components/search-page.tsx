"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Filter, Loader2 } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import type { Molecule } from "@/features/chemical-registration/types";
import { useProtocols } from "@/features/screening-assay/hooks/use-protocols";
import { useSdfExport } from "@/features/chemical-registration/hooks/use-sdf-export";
import type { SearchQuery, ActivityValue, SortField, SortDir, SavedSearch } from "../types";
import { useExecuteSearch, type EnrichedSearchResponse } from "../hooks/use-search";
import { useSavedSearches } from "../hooks/use-saved-searches";
import { useReportConfig } from "../hooks/use-report-config";
import { SearchForm } from "./search/search-form";
import { ProjectSidebar } from "./search/project-sidebar";
import { ResultsToolbar } from "./search/results-toolbar";
import { ResultsGrid } from "./search/results-grid";
import { CompoundDetailPanel } from "./search/compound-detail-panel";
import { ReportCustomizer } from "./search/report-customizer";
import { SaveSearchDialog } from "./search/save-search-dialog";
import { CollectionPickerDialog } from "./collection-picker-dialog";

// ─── Types ──────────────────────────────────────────────────────────────────

type EnrichedMolecule = Molecule & { activity?: Record<string, ActivityValue> };

// ─── Inner component (uses useSearchParams, needs Suspense boundary) ───────

function SearchPageInner() {
  const searchParams = useSearchParams();
  const savedSearchId = searchParams.get("saved");

  // ── Project scoping ────────────────────────────────────────────────────
  const [projectIds, setProjectIds] = useState<string[]>([]);

  // ── Search state ───────────────────────────────────────────────────────
  const [currentQuery, setCurrentQuery] = useState<SearchQuery | null>(null);
  const [protocolColumns, setProtocolColumns] = useState<string[]>([]);
  const [results, setResults] = useState<EnrichedMolecule[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [showForm, setShowForm] = useState(true);

  // ── Detail panel ───────────────────────────────────────────────────────
  const [selectedMolecule, setSelectedMolecule] = useState<EnrichedMolecule | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);

  // ── Dialogs ────────────────────────────────────────────────────────────
  const [reportOpen, setReportOpen] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  const [pickerMolIds, setPickerMolIds] = useState<string[]>([]);

  // ── Sorting ────────────────────────────────────────────────────────────
  const [sortBy, setSortBy] = useState<SortField | undefined>();
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  // ── Selection ──────────────────────────────────────────────────────────
  const [gridSelectedIds, setGridSelectedIds] = useState<Set<string>>(new Set());

  // ── Hooks ──────────────────────────────────────────────────────────────
  const searchMutation = useExecuteSearch();
  const { data: protocols } = useProtocols();
  const { data: savedSearches } = useSavedSearches();
  const { config: reportConfig, loadFromSavedSearch } = useReportConfig();
  const { exportSdf } = useSdfExport();

  // ── Derived: visible protocol IDs for detail panel ─────────────────────
  const visibleProtocolIds = useMemo(() => {
    return [
      ...new Set(
        protocolColumns
          .filter((c) => c.startsWith("drc:"))
          .map((c) => c.split(":")[1]),
      ),
    ];
  }, [protocolColumns]);

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
      setCurrentQuery(query);
      setProtocolColumns(columns);
      setShowForm(false);
      setHasSearched(true);
      setSelectedMolecule(null);
      setGridSelectedIds(new Set());

      const input = {
        query,
        ...(columns.length > 0 ? { protocol_columns: columns } : {}),
      };

      searchMutation.mutate(
        { input, limit: 100, sort_by: sortBy, sort_dir: sortDir },
        {
          onSuccess: (data) => {
            setResults(enrichItems(data));
            setNextCursor(data.next_cursor);
            setTotalCount(data.total_count);
          },
        },
      );
    },
    [searchMutation, sortBy, sortDir, enrichItems],
  );

  // ── handleLoadMore ─────────────────────────────────────────────────────
  const handleLoadMore = useCallback(() => {
    if (!currentQuery || !nextCursor) return;
    const input = {
      query: currentQuery,
      ...(protocolColumns.length > 0 ? { protocol_columns: protocolColumns } : {}),
    };

    searchMutation.mutate(
      { input, cursor: nextCursor, limit: 100, sort_by: sortBy, sort_dir: sortDir },
      {
        onSuccess: (data) => {
          setResults((prev) => [...prev, ...enrichItems(data)]);
          setNextCursor(data.next_cursor);
          setTotalCount(data.total_count);
        },
      },
    );
  }, [currentQuery, nextCursor, searchMutation, protocolColumns, sortBy, sortDir, enrichItems]);

  // ── Load saved search from URL ─────────────────────────────────────────
  const savedSearchLoadedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!savedSearchId || !savedSearches) return;
    if (savedSearchLoadedRef.current === savedSearchId) return;
    savedSearchLoadedRef.current = savedSearchId;

    const saved = savedSearches.find((s: SavedSearch) => s.id === savedSearchId);
    if (!saved) return;

    // Restore report config
    loadFromSavedSearch(saved.columns);

    // Restore protocol columns from saved search
    const cols = saved.columns as { protocolColumns?: string[] } | null;
    const restoredColumns = cols?.protocolColumns ?? [];

    // Execute the search
    const query = saved.query as unknown as SearchQuery;
    if (query?.criteria) {
      handleSearch(query, restoredColumns);
    }
  }, [savedSearchId, savedSearches, loadFromSavedSearch, handleSearch]);

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
    setGridSelectedIds(new Set(results.map((m) => m.id)));
  }, [results]);

  const handleSelectNone = useCallback(() => {
    setGridSelectedIds(new Set());
  }, []);

  // ── Row click -> detail panel ──────────────────────────────────────────
  const handleRowClick = useCallback(
    (molecule: EnrichedMolecule) => {
      const idx = results.findIndex((m) => m.id === molecule.id);
      setSelectedMolecule(molecule);
      setSelectedIndex(idx >= 0 ? idx : 0);
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
      setSelectedIndex(nextIdx);
      setSelectedMolecule(results[nextIdx] ?? null);
    },
    [selectedIndex, results],
  );

  // ─── Layout ────────────────────────────────────────────────────────────

  return (
    <div className="flex h-[calc(100vh-64px)]">
      {/* ── Left: Project Sidebar ── */}
      <ProjectSidebar selectedIds={projectIds} onChange={setProjectIds} />

      {/* ── Center: Search form + results ── */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Search form (collapsible) */}
        {showForm && (
          <div className="shrink-0 overflow-auto border-b p-4">
            <SearchForm
              initialQuery={currentQuery ?? undefined}
              projectIds={projectIds}
              onProjectsChange={setProjectIds}
              onSearch={handleSearch}
              isLoading={searchMutation.isPending}
            />
          </div>
        )}

        {/* "Refine Search" button when form is collapsed */}
        {!showForm && hasSearched && (
          <div className="shrink-0 border-b px-4 py-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowForm(true)}
            >
              <Filter className="mr-2 h-4 w-4" />
              Refine Search
            </Button>
          </div>
        )}

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

            {/* Grid area */}
            <div className="flex-1 overflow-hidden">
              <ResultsGrid
                results={results}
                protocolColumns={protocolColumns}
                protocols={protocols ?? []}
                reportConfig={reportConfig}
                loading={searchMutation.isPending && results.length === 0}
                onRowClick={handleRowClick}
                selectedIds={gridSelectedIds}
                onSelectionChange={setGridSelectedIds}
              />
            </div>

            {/* Load more */}
            {nextCursor && (
              <div className="shrink-0 border-t py-3 text-center">
                <Button
                  variant="outline"
                  onClick={handleLoadMore}
                  disabled={searchMutation.isPending}
                >
                  {searchMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Loading...
                    </>
                  ) : (
                    "Load More"
                  )}
                </Button>
              </div>
            )}
          </>
        )}

        {/* Empty state before first search */}
        {!hasSearched && !showForm && (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
            Build a query to search compounds.
          </div>
        )}
      </div>

      {/* ── Right: Compound Detail Panel (conditional) ── */}
      {selectedMolecule && (
        <div className="w-[420px] shrink-0">
          <CompoundDetailPanel
            molecule={selectedMolecule}
            visibleProtocolIds={visibleProtocolIds}
            currentIndex={selectedIndex}
            totalCount={results.length}
            onNavigate={handleDetailNavigate}
            onClose={() => setSelectedMolecule(null)}
          />
        </div>
      )}

      {/* ── Dialogs ── */}
      <ReportCustomizer
        open={reportOpen}
        onClose={() => setReportOpen(false)}
        protocols={protocols ?? []}
        activeProtocolIds={visibleProtocolIds}
      />

      {currentQuery && (
        <SaveSearchDialog
          open={saveOpen}
          onClose={() => setSaveOpen(false)}
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
