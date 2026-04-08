"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BookmarkPlus, ChevronDown, Download, ListPlus, Star } from "lucide-react";
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
import { showSuccess } from "@/shared/lib/toast";
import { useSdfExport } from "@/features/chemical-registration/hooks/use-sdf-export";
import type {
  Molecule,
  LifecycleStage,
} from "@/features/chemical-registration/types";
import { LIFECYCLE_LABELS } from "@/features/chemical-registration/types";
import { useProtocols } from "@/features/screening-assay/hooks/use-protocols";
import type { Protocol } from "@/features/screening-assay/types";
import { usePreferencesStore } from "@/shared/lib/stores/preferences-store";
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

// ─── Protocol column selector ──────────────────────────────────────────────

const CURVE_TYPES = ["ic50", "ec50", "ki", "kd"] as const;

function ProtocolColumnSelector({
  protocols,
  selected,
  onChange,
}: {
  protocols: Protocol[];
  selected: string[];
  onChange: (cols: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const activeProtocols = protocols.filter((p) => p.status === "active");

  function toggle(colId: string) {
    onChange(
      selected.includes(colId)
        ? selected.filter((c) => c !== colId)
        : [...selected, colId]
    );
  }

  if (activeProtocols.length === 0) return null;

  return (
    <div className="mb-3 rounded-md border bg-muted/20 px-3 py-2">
      <button
        type="button"
        className="flex w-full items-center justify-between text-sm"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="font-medium">
          Protocol Columns{" "}
          <span className="text-muted-foreground font-normal">
            ({selected.length} selected)
          </span>
        </span>
        <ChevronDown
          className={`h-4 w-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div className="mt-3 space-y-3 max-h-64 overflow-y-auto">
          {activeProtocols.map((p) => {
            const numericRds = p.readout_definitions.filter(
              (rd) => rd.data_type === "numeric"
            );
            return (
              <div key={p.id} className="border-b border-border/50 pb-2 last:border-0">
                <span className="text-xs font-semibold text-foreground">{p.name}</span>
                <div className="mt-1 ml-2 flex flex-wrap gap-x-4 gap-y-1">
                  {numericRds.length > 0 && (
                    <div className="flex flex-wrap gap-x-3 gap-y-1">
                      {numericRds.map((rd) => {
                        const colId = `rd:${rd.id}`;
                        return (
                          <label key={rd.id} className="flex items-center gap-1.5 text-xs cursor-pointer">
                            <input
                              type="checkbox"
                              className="rounded"
                              checked={selected.includes(colId)}
                              onChange={() => toggle(colId)}
                            />
                            {rd.name}
                            {rd.unit ? ` (${rd.unit})` : ""}
                          </label>
                        );
                      })}
                    </div>
                  )}
                  <div className="flex flex-wrap gap-x-3 gap-y-1">
                    {CURVE_TYPES.map((ct) => {
                      const colId = `drc:${p.id}:${ct}`;
                      return (
                        <label key={ct} className="flex items-center gap-1.5 text-xs cursor-pointer">
                          <input
                            type="checkbox"
                            className="rounded"
                            checked={selected.includes(colId)}
                            onChange={() => toggle(colId)}
                          />
                          <span className="italic text-muted-foreground">{ct.toUpperCase()} (curve)</span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Main component ─────────────────────────────────────────────────────────

export function SearchPage() {
  const [results, setResults] = useState<EnrichedMolecule[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [currentQuery, setCurrentQuery] = useState<SearchQuery | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [protocolColumns, setProtocolColumns] = useState<string[]>([]);

  // Load default columns from preferences on mount
  const { defaultSearchColumns, setDefaultSearchColumns } = usePreferencesStore();
  const defaultsLoadedRef = useRef(false);
  useEffect(() => {
    if (!defaultsLoadedRef.current && defaultSearchColumns?.length) {
      setProtocolColumns(defaultSearchColumns);
      defaultsLoadedRef.current = true;
    }
  }, [defaultSearchColumns]);

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
      } else if (parts[0] === "rd" && protocols) {
        // Find the readout definition across all protocols
        for (const proto of protocols) {
          const rd = proto.readout_definitions.find((r) => r.id === parts[1]);
          if (rd) {
            headerName = `${proto.name} — ${rd.name}${rd.unit ? ` (${rd.unit})` : ""}`;
            break;
          }
        }
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
        width: 140,
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
      // Restore protocol columns from saved search
      const cols = saved.columns as { protocol_columns?: string[] } | null;
      if (cols?.protocol_columns) {
        setProtocolColumns(cols.protocol_columns);
      }
      const query = saved.query as unknown as SearchQuery;
      if (query?.criteria) {
        handleSearch(query);
      }
    },
    [savedSearches, handleSearch]
  );

  const { exportSdf } = useSdfExport();
  const handleExportSdf = useCallback(() => {
    if (!currentQuery || !results.length) return;
    exportSdf(results.map((m) => m.id), "search-results.sdf");
  }, [currentQuery, results, exportSdf]);

  const handleSaveSearch = useCallback(() => {
    if (!saveName.trim() || !currentQuery) return;
    createSavedSearch.mutate(
      {
        name: saveName.trim(),
        query: currentQuery as unknown as Record<string, unknown>,
        columns: protocolColumns.length > 0 ? { protocol_columns: protocolColumns } : null,
      },
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

          {protocols?.length ? (
            <div className="mb-3 flex items-start gap-2">
              <div className="flex-1">
                <ProtocolColumnSelector
                  protocols={protocols}
                  selected={protocolColumns}
                  onChange={setProtocolColumns}
                />
              </div>
              {protocolColumns.length > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-1 shrink-0"
                  onClick={() => {
                    setDefaultSearchColumns(protocolColumns);
                    showSuccess("Default columns saved");
                  }}
                  title="Save current protocol columns as default"
                >
                  <Star className="mr-1 h-3.5 w-3.5" />
                  Set Default
                </Button>
              )}
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
