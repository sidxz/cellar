"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { FileUp } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { Textarea } from "@/shared/components/ui/textarea";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useMapWells } from "../hooks/use-plates";
import type { WellMapping } from "../types/plates";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function plateDimensions(format: string): { rows: number; cols: number } {
  const f = parseInt(format, 10);
  if (f === 6) return { rows: 2, cols: 3 };
  if (f === 12) return { rows: 3, cols: 4 };
  if (f === 24) return { rows: 4, cols: 6 };
  if (f === 48) return { rows: 6, cols: 8 };
  if (f === 384) return { rows: 16, cols: 24 };
  if (f === 1536) return { rows: 32, cols: 48 };
  return { rows: 8, cols: 12 }; // 96 default
}

function rowLabels(count: number): string[] {
  return "ABCDEFGHIJKLMNOPQRSTUVWXYZ".slice(0, count).split("");
}

/**
 * Parse CSV text with well mappings.
 * Expected format: Well,BatchNumber,Concentration,Unit
 * e.g.: A1,CV-00001-001,10,mM
 */
function parseCsvWellMap(text: string): Record<string, WellMapping> {
  const map: Record<string, WellMapping> = {};
  const lines = text.trim().split("\n");
  for (const line of lines) {
    const parts = line.split(/[,\t]/).map((s) => s.trim());
    if (parts.length < 2) continue;
    const [well, batchId, concStr, unit] = parts;
    // Skip header rows
    if (!well || /^well$/i.test(well) || /^position$/i.test(well)) continue;
    // Validate well position format (letter(s) + number)
    if (!/^[A-Z]{1,2}\d{1,2}$/i.test(well)) continue;
    const pos = well.toUpperCase();
    map[pos] = {
      batch_id: batchId,
      concentration_value: concStr ? parseFloat(concStr) || null : null,
      concentration_unit: concStr && parseFloat(concStr) ? (unit || "mM") : null,
    };
  }
  return map;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// PlateGrid — measures its container and computes square cell sizes
// ---------------------------------------------------------------------------

interface PlateGridProps {
  rows: number;
  cols: number;
  letters: string[];
  wellMap: Record<string, WellMapping>;
  selectedWell: string | null;
  onSelectWell: (pos: string) => void;
}

function PlateGrid({ rows, cols, letters, wellMap, selectedWell, onSelectWell }: PlateGridProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [cellSize, setCellSize] = useState(0);
  const LABEL_SIZE = 24; // px reserved for row/col labels
  const GAP = 2; // px between cells

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const measure = () => {
      const rect = el.getBoundingClientRect();
      const availW = rect.width - LABEL_SIZE - GAP * cols;
      const availH = rect.height - LABEL_SIZE - GAP * rows;
      const size = Math.max(Math.floor(Math.min(availW / cols, availH / rows)), 8);
      setCellSize(size);
    };

    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [cols, rows]);

  return (
    <div ref={containerRef} className="flex-1 min-w-0 flex items-center justify-center">
      {cellSize > 0 && (
        <div
          className="inline-grid"
          style={{
            gridTemplateColumns: `${LABEL_SIZE}px repeat(${cols}, ${cellSize}px)`,
            gridTemplateRows: `${LABEL_SIZE}px repeat(${rows}, ${cellSize}px)`,
            gap: `${GAP}px`,
          }}
        >
          {/* Top-left corner */}
          <div />
          {/* Column headers */}
          {Array.from({ length: cols }, (_, i) => (
            <div
              key={`col-${i}`}
              className="flex items-center justify-center text-xs text-muted-foreground font-mono"
            >
              {i + 1}
            </div>
          ))}
          {/* Rows */}
          {letters.map((row) => (
            <Fragment key={`row-${row}`}>
              <div className="flex items-center justify-center text-xs text-muted-foreground font-mono">
                {row}
              </div>
              {Array.from({ length: cols }, (_, i) => {
                const pos = `${row}${i + 1}`;
                const well = wellMap[pos];
                const isSelected = selectedWell === pos;
                return (
                  <button
                    key={pos}
                    type="button"
                    onClick={() => onSelectWell(pos)}
                    title={
                      well
                        ? `${pos}: ${well.batch_id} @ ${well.concentration_value ?? "\u2014"} ${well.concentration_unit ?? ""}`
                        : pos
                    }
                    className={`rounded-sm border transition-colors flex items-center justify-center font-mono
                      ${cellSize > 28 ? "text-[10px]" : "text-[7px]"}
                      ${isSelected ? "ring-2 ring-primary border-primary" : ""}
                      ${well ? "bg-primary/60 border-primary/40 text-primary-foreground" : "bg-muted/30 border-muted hover:bg-muted/60"}
                    `}
                  />
                );
              })}
            </Fragment>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dialog
// ---------------------------------------------------------------------------

interface WellMappingDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  plateId: string;
  format: string;
  initialWellMap: Record<string, WellMapping> | null;
}

export function WellMappingDialog({
  open,
  onOpenChange,
  plateId,
  format,
  initialWellMap,
}: WellMappingDialogProps) {
  const { rows, cols } = plateDimensions(format);
  const letters = rowLabels(rows);
  const mapWells = useMapWells(plateId);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Local editable copy of well_map
  const [wellMap, setWellMap] = useState<Record<string, WellMapping>>({});
  const [selectedWell, setSelectedWell] = useState<string | null>(null);
  const [batchId, setBatchId] = useState("");
  const [concValue, setConcValue] = useState("");
  const [concUnit, setConcUnit] = useState("mM");
  const [csvText, setCsvText] = useState("");

  useEffect(() => {
    if (open) {
      setWellMap(initialWellMap ? { ...initialWellMap } : {});
      setSelectedWell(null);
      setBatchId("");
      setConcValue("");
      setCsvText("");
    }
  }, [open, initialWellMap]);

  const assignWell = useCallback(() => {
    if (!selectedWell || !batchId.trim()) return;
    setWellMap((prev) => ({
      ...prev,
      [selectedWell]: {
        batch_id: batchId.trim(),
        concentration_value: concValue ? parseFloat(concValue) : null,
        concentration_unit: concValue ? concUnit : null,
      },
    }));
    // Move to next well
    const rowIdx = letters.indexOf(selectedWell[0]);
    const colIdx = parseInt(selectedWell.slice(1), 10);
    if (colIdx < cols) {
      setSelectedWell(`${letters[rowIdx]}${colIdx + 1}`);
    } else if (rowIdx + 1 < rows) {
      setSelectedWell(`${letters[rowIdx + 1]}1`);
    } else {
      setSelectedWell(null);
    }
    setBatchId("");
    setConcValue("");
  }, [selectedWell, batchId, concValue, concUnit, letters, cols, rows]);

  const clearWell = useCallback(() => {
    if (!selectedWell) return;
    setWellMap((prev) => {
      const next = { ...prev };
      delete next[selectedWell];
      return next;
    });
  }, [selectedWell]);

  const handleCsvImport = () => {
    const parsed = parseCsvWellMap(csvText);
    const count = Object.keys(parsed).length;
    if (count === 0) {
      showError("No valid well mappings found in the pasted data.");
      return;
    }
    setWellMap((prev) => ({ ...prev, ...parsed }));
    showSuccess(`Mapped ${count} wells from pasted data`);
    setCsvText("");
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target?.result as string;
      const parsed = parseCsvWellMap(text);
      const count = Object.keys(parsed).length;
      if (count === 0) {
        showError("No valid well mappings found in the file.");
        return;
      }
      setWellMap((prev) => ({ ...prev, ...parsed }));
      showSuccess(`Mapped ${count} wells from file`);
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  const handleSave = () => {
    mapWells.mutate(wellMap, {
      onSuccess: () => onOpenChange(false),
    });
  };

  const handleDownloadTemplate = () => {
    const header = "Well,Batch Number,Concentration,Unit";
    const examples = [
      "A1,CV-00001-001,10,mM",
      "A2,CV-00002-001,10,mM",
      "B1,CV-00003-001,5,mM",
    ];
    const csv = [header, ...examples].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "well_mapping_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const mappedCount = Object.keys(wellMap).length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="flex flex-col"
        style={{
          width: "92vw",
          maxWidth: "92vw",
          height: "80vh",
          maxHeight: "80vh",
        }}
      >
        <DialogHeader className="shrink-0">
          <DialogTitle>Map Wells to Batches</DialogTitle>
          <DialogDescription>
            Assign compound batches to wells — click individually or paste/upload a CSV.
            {mappedCount > 0 && ` (${mappedCount} wells mapped)`}
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 min-h-0 flex gap-6 overflow-hidden">
          {/* Plate grid — measured container, computed cell size */}
          <PlateGrid
            rows={rows}
            cols={cols}
            letters={letters}
            wellMap={wellMap}
            selectedWell={selectedWell}
            onSelectWell={(pos) => {
              setSelectedWell(pos);
              const well = wellMap[pos];
              if (well) {
                setBatchId(well.batch_id);
                setConcValue(well.concentration_value?.toString() ?? "");
                setConcUnit(well.concentration_unit ?? "mM");
              } else {
                setBatchId("");
                setConcValue("");
              }
            }}
          />

          {/* Right panel — tabs for click-assign vs CSV import */}
          <div className="w-80 shrink-0 border-l pl-4 overflow-auto">
            <Tabs defaultValue="click">
              <TabsList className="w-full">
                <TabsTrigger value="click" className="flex-1">Click to Assign</TabsTrigger>
                <TabsTrigger value="csv" className="flex-1">Paste / Upload CSV</TabsTrigger>
              </TabsList>

              <TabsContent value="click" className="mt-4 space-y-4">
                {selectedWell ? (
                  <>
                    <div>
                      <p className="text-sm font-medium">
                        Well <span className="font-mono text-primary text-lg">{selectedWell}</span>
                      </p>
                      {wellMap[selectedWell] && (
                        <p className="text-xs text-muted-foreground mt-1">
                          Currently: {wellMap[selectedWell].batch_id}
                        </p>
                      )}
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="batch-id">Batch #</Label>
                      <Input
                        id="batch-id"
                        placeholder="e.g. CV-00001-001"
                        value={batchId}
                        onChange={(e) => setBatchId(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") assignWell();
                        }}
                        autoFocus
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div className="space-y-2">
                        <Label htmlFor="conc-value">Concentration</Label>
                        <Input
                          id="conc-value"
                          type="number"
                          step="any"
                          placeholder="10"
                          value={concValue}
                          onChange={(e) => setConcValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") assignWell();
                          }}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="conc-unit">Unit</Label>
                        <Input
                          id="conc-unit"
                          placeholder="mM"
                          value={concUnit}
                          onChange={(e) => setConcUnit(e.target.value)}
                        />
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" onClick={assignWell} disabled={!batchId.trim()}>
                        Assign & Next
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={clearWell}
                        disabled={!wellMap[selectedWell]}
                      >
                        Clear
                      </Button>
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground py-4">
                    Click a well on the plate to assign a batch.
                  </p>
                )}
              </TabsContent>

              <TabsContent value="csv" className="mt-4 space-y-4">
                <div>
                  <p className="text-sm text-muted-foreground mb-3">
                    Paste CSV data or upload a file. Format: <code className="text-xs bg-muted px-1 py-0.5 rounded">Well, Batch#, Concentration, Unit</code>
                  </p>
                  <Textarea
                    placeholder={"A1,CV-00001-001,10,mM\nA2,CV-00002-001,10,mM\nB1,CV-00003-001,5,mM"}
                    rows={8}
                    value={csvText}
                    onChange={(e) => setCsvText(e.target.value)}
                    className="font-mono text-xs"
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={handleCsvImport}
                    disabled={!csvText.trim()}
                  >
                    Apply Pasted Data
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <FileUp className="mr-1.5 h-3.5 w-3.5" />
                    Upload CSV
                  </Button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,.tsv,.txt"
                    className="hidden"
                    onChange={handleFileUpload}
                  />
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-xs"
                  onClick={handleDownloadTemplate}
                >
                  Download template CSV
                </Button>
              </TabsContent>
            </Tabs>

            {/* Clear all */}
            {mappedCount > 0 && (
              <div className="mt-6 pt-4 border-t">
                <Button
                  size="sm"
                  variant="ghost"
                  className="text-destructive hover:text-destructive text-xs"
                  onClick={() => setWellMap({})}
                >
                  Clear all {mappedCount} wells
                </Button>
              </div>
            )}
          </div>
        </div>

        <DialogFooter className="shrink-0">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={mapWells.isPending}>
            {mapWells.isPending ? "Saving..." : `Save Well Map (${mappedCount} wells)`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
