"use client";

import { useCallback, useMemo, useState } from "react";
import { BookmarkPlus, Download, ListPlus } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { downloadFile } from "@/shared/lib/api/download";
import { showSuccess } from "@/shared/lib/toast";
import type {
  Molecule,
  LifecycleStage,
} from "@/features/chemical-registration/types";
import { LIFECYCLE_LABELS } from "@/features/chemical-registration/types";
import { useProtocols } from "@/features/screening-assay/hooks/use-protocols";
import type { ActivityValue } from "../types";
import { useExecuteSearch } from "../hooks/use-search";
import {
  useSavedSearches,
  useCreateSavedSearch,
} from "../hooks/use-saved-searches";
import { SearchQueryBuilder } from "./search-query-builder";
import { CollectionPickerDialog } from "./collection-picker-dialog";
import type { SearchQuery, SavedSearch } from "../types";

// ─── Types ──────────────────────────────────────────────────────────────────

type EnrichedMolecule = Molecule & { activity?: Record<string, ActivityValue> };

// ─── Results grid columns ───────────────────────────────────────────────────

function buildColumnDefs(): ColDef<EnrichedMolecule>[] {
  return [
    {
      headerName: "Structure",
      width: 72,
      sortable: false,
      filter: false,
      cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => {
        const smiles = params.data?.structure?.smiles;
        if (!smiles) return <div className="h-10 w-10 rounded bg-muted" />;
        return <StructureThumbnail smiles={smiles} size={48} />;
      },
    },
    {
      headerName: "Reg #",
      field: "registration_number",
      width: 120,
      cellClass: "font-mono text-xs",
    },
    {
      headerName: "Name",
      field: "name",
      flex: 1,
      minWidth: 150,
    },
    {
      headerName: "MW",
      width: 90,
      valueGetter: (p) => p.data?.descriptors?.molecular_weight ?? null,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(1) : "\u2014"),
    },
    {
      headerName: "LogP",
      width: 80,
      valueGetter: (p) => p.data?.descriptors?.logp ?? null,
      valueFormatter: (p) => (p.value != null ? Number(p.value).toFixed(2) : "\u2014"),
    },
    {
      headerName: "Stage",
      field: "lifecycle_stage",
      width: 120,
      cellRenderer: (params: ICellRendererParams<EnrichedMolecule>) => {
        const stage = params.value as LifecycleStage | undefined;
        if (!stage) return "\u2014";
        return (
          <Badge variant="outline" className="text-xs">
            {LIFECYCLE_LABELS[stage] ?? stage}
          </Badge>
        );
      },
    },
  ];
}

// ─── Main component ─────────────────────────────────────────────────────────

export function SearchPage() {
  const [results, setResults] = useState<EnrichedMolecule[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [currentQuery, setCurrentQuery] = useState<SearchQuery | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [protocolColumns, setProtocolColumns] = useState<string[]>([]);

  // Save search dialog state
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [pickerMolIds, setPickerMolIds] = useState<string[]>([]);

  const searchMutation = useExecuteSearch();
  const { data: savedSearches } = useSavedSearches();
  const createSavedSearch = useCreateSavedSearch();
  const { data: protocols } = useProtocols();

  const columnDefs = useMemo(buildColumnDefs, []);

  const dynamicColumnDefs = useMemo(() => {
    return protocolColumns.map((colId) => {
      const parts = colId.split(":");
      let headerName = colId;
      if (parts[0] === "drc" && protocols) {
        const proto = protocols.find((p) => p.id === parts[1]);
        headerName = `${proto?.name ?? "?"} ${parts[2]?.toUpperCase()}`;
      }
      return {
        headerName,
        valueGetter: (params: { data?: EnrichedMolecule }) => {
          return params.data?.activity?.[colId]?.value ?? null;
        },
        valueFormatter: (params: { value: number | null; data?: EnrichedMolecule }) => {
          const av = params.data?.activity?.[colId];
          if (!av?.value) return "";
          const q = av.qualifier && av.qualifier !== "=" ? `${av.qualifier} ` : "";
          return `${q}${av.value.toPrecision(4)}${av.unit ? ` ${av.unit}` : ""}`;
        },
        width: 130,
        sortable: true,
      };
    });
  }, [protocolColumns, protocols]);

  const allColumnDefs = useMemo(
    () => [...columnDefs, ...dynamicColumnDefs],
    [columnDefs, dynamicColumnDefs]
  );

  const handleSearch = useCallback(
    (query: SearchQuery) => {
      setCurrentQuery(query);
      setHasSearched(true);
      const input = {
        query,
        ...(protocolColumns.length > 0 ? { protocol_columns: protocolColumns } : {}),
      };
      searchMutation.mutate(
        { input, limit: 100 },
        {
          onSuccess: (data) => {
            const enrichedItems: EnrichedMolecule[] = data.items.map((mol) => ({
              ...mol,
              activity: data.activity_data?.[mol.id] ?? undefined,
            }));
            setResults(enrichedItems);
            setNextCursor(data.next_cursor);
            setTotalCount(data.total_count);
          },
        }
      );
    },
    [searchMutation, protocolColumns]
  );

  const handleLoadMore = useCallback(() => {
    if (!currentQuery || !nextCursor) return;
    const input = {
      query: currentQuery,
      ...(protocolColumns.length > 0 ? { protocol_columns: protocolColumns } : {}),
    };
    searchMutation.mutate(
      { input, cursor: nextCursor, limit: 100 },
      {
        onSuccess: (data) => {
          const enrichedItems: EnrichedMolecule[] = data.items.map((mol) => ({
            ...mol,
            activity: data.activity_data?.[mol.id] ?? undefined,
          }));
          setResults((prev) => [...prev, ...enrichedItems]);
          setNextCursor(data.next_cursor);
          setTotalCount(data.total_count);
        },
      }
    );
  }, [currentQuery, nextCursor, searchMutation, protocolColumns]);

  const handleLoadSavedSearch = useCallback(
    (searchId: string) => {
      const saved = savedSearches?.find((s: SavedSearch) => s.id === searchId);
      if (!saved) return;
      const query = saved.query as unknown as SearchQuery;
      if (query?.criteria) {
        handleSearch(query);
      }
    },
    [savedSearches, handleSearch]
  );

  const handleExportSdf = useCallback(() => {
    if (!currentQuery) return;
    downloadFile({
      url: "/api/v1/molecules/export/sdf",
      method: "POST",
      data: {
        molecule_ids: results.map((m) => m.id),
      },
      filename: "search-results.sdf",
    });
  }, [currentQuery, results]);

  const handleSaveSearch = useCallback(() => {
    if (!saveName.trim() || !currentQuery) return;
    createSavedSearch.mutate(
      { name: saveName.trim(), query: currentQuery as unknown as Record<string, unknown> },
      {
        onSuccess: () => {
          setSaveOpen(false);
          setSaveName("");
          showSuccess("Search saved successfully");
        },
      }
    );
  }, [saveName, currentQuery, createSavedSearch]);

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Compound Search</h1>
        <p className="mt-1 text-muted-foreground">
          Build compound queries with text, property, and structure criteria.
        </p>
      </div>

      {/* Saved search selector */}
      {savedSearches && savedSearches.length > 0 && (
        <div className="mb-4 flex items-center gap-2">
          <Label className="text-sm text-muted-foreground">Load saved search:</Label>
          <Select onValueChange={handleLoadSavedSearch}>
            <SelectTrigger className="h-9 w-64">
              <SelectValue placeholder="Select a saved search..." />
            </SelectTrigger>
            <SelectContent>
              {savedSearches.map((s: SavedSearch) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Query builder */}
      <SearchQueryBuilder
        initialQuery={currentQuery ?? undefined}
        onSearch={handleSearch}
        isLoading={searchMutation.isPending}
      />

      {/* Results */}
      {hasSearched && (
        <div className="mt-6">
          {/* Results toolbar */}
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              {totalCount != null
                ? `${totalCount.toLocaleString()} result${totalCount === 1 ? "" : "s"} found`
                : `${results.length} result${results.length === 1 ? "" : "s"} loaded`}
            </p>
            <div className="flex items-center gap-2">
              {currentQuery && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSaveOpen(true)}
                >
                  <BookmarkPlus className="mr-2 h-4 w-4" />
                  Save Search
                </Button>
              )}
              {results.length > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleExportSdf}
                >
                  <Download className="mr-2 h-4 w-4" />
                  Export SDF
                </Button>
              )}
            </div>
          </div>

          {results.length > 0 && protocols?.length ? (
            <div className="mb-2">
              <details className="text-sm">
                <summary className="cursor-pointer text-muted-foreground">
                  Protocol columns ({protocolColumns.length} selected)
                </summary>
                <div className="mt-2 space-y-1 max-h-48 overflow-y-auto">
                  {protocols.filter((p) => p.status === "active").map((p) => (
                    <div key={p.id} className="pl-2">
                      <span className="text-xs font-medium">{p.name}</span>
                      <div className="ml-3 flex flex-wrap gap-2">
                        {["ic50", "ec50"].map((ct) => {
                          const colId = `drc:${p.id}:${ct}`;
                          return (
                            <label key={ct} className="flex items-center gap-1 text-xs">
                              <input
                                type="checkbox"
                                checked={protocolColumns.includes(colId)}
                                onChange={(e) => {
                                  setProtocolColumns((prev) =>
                                    e.target.checked
                                      ? [...prev, colId]
                                      : prev.filter((c) => c !== colId)
                                  );
                                }}
                              />
                              {ct.toUpperCase()}
                            </label>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            </div>
          ) : null}

          <DataGrid<EnrichedMolecule>
            rowData={results}
            columnDefs={allColumnDefs}
            loading={searchMutation.isPending && results.length === 0}
            height="500px"
            exportFilename="search-results"
            selectionToolbar={(selected) => (
              <>
                <span className="text-sm text-muted-foreground">
                  {selected.length} selected
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setPickerMolIds(selected.map((m) => m.id))}
                >
                  <ListPlus className="mr-1 h-4 w-4" />
                  Add to Collection
                </Button>
              </>
            )}
            emptyState={
              <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
                <h3 className="text-lg font-semibold">No results</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  Try adjusting your search criteria.
                </p>
              </div>
            }
          />

          <CollectionPickerDialog
            open={pickerMolIds.length > 0}
            onOpenChange={(open) => {
              if (!open) setPickerMolIds([]);
            }}
            moleculeIds={pickerMolIds}
            onComplete={() => setPickerMolIds([])}
          />

          {/* Load more */}
          {nextCursor && (
            <div className="mt-4 flex justify-center">
              <Button
                variant="outline"
                onClick={handleLoadMore}
                disabled={searchMutation.isPending}
              >
                {searchMutation.isPending ? "Loading..." : "Load More"}
              </Button>
            </div>
          )}
        </div>
      )}

      {/* Save search dialog */}
      <Dialog open={saveOpen} onOpenChange={setSaveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save Search</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Label htmlFor="search-name">Name</Label>
            <Input
              id="search-name"
              className="mt-2"
              placeholder="My search..."
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSaveSearch();
              }}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSaveOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSaveSearch}
              disabled={!saveName.trim() || createSavedSearch.isPending}
            >
              {createSavedSearch.isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
