"use client";

import { WELL_TYPE_LABELS, type WellType } from "@/features/screening-assay/types";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { Textarea } from "@/shared/components/ui/textarea";
import { saveText } from "@/shared/lib/api/download";
import { parseCsvRows } from "@/shared/lib/parse-csv";
import { showError, showSuccess } from "@/shared/lib/toast";
import { FileUp } from "lucide-react";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { useMapWells } from "../hooks/use-plates";
import type { WellMapping } from "../types/plates";
import { BatchSearchPicker } from "./batch-search-picker";

const CONCENTRATION_UNITS = ["mM", "uM", "nM", "mg/mL"] as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function plateDimensions(format: string): { rows: number; cols: number } {
  const f = Number.parseInt(format, 10);
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
 * Expected format: Well,BatchNumber,Concentration,Unit,Role
 * e.g.: A1,CC-000001-001,10,mM,sample
 * Role is optional and defaults to "sample"; unknown roles fall back to sample.
 */
function parseCsvWellMap(text: string): Record<string, WellMapping> {
  const map: Record<string, WellMapping> = {};
  const validRoles = Object.keys(WELL_TYPE_LABELS);
  // Positional/headerless format with comma- or tab-separated columns. Parsed
  // via the shared PapaParse helper so quoted/comma-containing fields don't
  // mis-split; header detection + validation stays here.
  for (const parts of parseCsvRows(text)) {
    if (parts.length < 2) continue;
    const [well, batchId, concStr, unit, roleStr] = parts;
    // Skip header rows
    if (!well || /^well$/i.test(well) || /^position$/i.test(well)) continue;
    // Validate well position format (letter(s) + number)
    if (!/^[A-Z]{1,2}\d{1,2}$/i.test(well)) continue;
    const pos = well.toUpperCase();
    const role = roleStr?.toLowerCase().replace(/\s+/g, "_");
    map[pos] = {
      batch_id: batchId,
      concentration_value: concStr ? Number.parseFloat(concStr) || null : null,
      concentration_unit: concStr && Number.parseFloat(concStr) ? unit || "mM" : null,
      well_type: role && validRoles.includes(role) ? role : "sample",
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
          {Array.from({ length: cols }, (_, i) => {
            const colNum = i + 1;
            return (
              <div
                key={`col-${colNum}`}
                className="flex items-center justify-center text-xs text-muted-foreground font-mono"
              >
                {colNum}
              </div>
            );
          })}
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
                        ? `${pos} \u00b7 ${WELL_TYPE_LABELS[(well.well_type ?? "sample") as WellType]}${well.batch_id ? ` \u00b7 ${well.batch_id}` : ""}${well.concentration_value != null ? ` @ ${well.concentration_value} ${well.concentration_unit ?? ""}` : ""}`
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
  const [role, setRole] = useState<string>("sample");
  const [csvText, setCsvText] = useState("");

  useEffect(() => {
    if (open) {
      setWellMap(initialWellMap ? { ...initialWellMap } : {});
      setSelectedWell(null);
      setBatchId("");
      setConcValue("");
      setRole("sample");
      setCsvText("");
    }
  }, [open, initialWellMap]);

  const assignWell = useCallback(() => {
    if (!selectedWell) return;
    // A sample well needs a batch; control / blank wells may have none.
    if (!batchId.trim() && role === "sample") return;
    setWellMap((prev) => ({
      ...prev,
      [selectedWell]: {
        batch_id: batchId.trim(),
        concentration_value: concValue ? Number.parseFloat(concValue) : null,
        concentration_unit: concValue ? concUnit : null,
        well_type: role,
      },
    }));
    // Move to next well
    const rowIdx = letters.indexOf(selectedWell[0]);
    const colIdx = Number.parseInt(selectedWell.slice(1), 10);
    if (colIdx < cols) {
      setSelectedWell(`${letters[rowIdx]}${colIdx + 1}`);
    } else if (rowIdx + 1 < rows) {
      setSelectedWell(`${letters[rowIdx + 1]}1`);
    } else {
      setSelectedWell(null);
    }
    setBatchId("");
    setConcValue("");
    setRole("sample");
  }, [selectedWell, batchId, concValue, concUnit, role, letters, cols, rows]);

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
    const header = "Well,Batch Number,Concentration,Unit,Role";
    const examples = [
      "A1,CC-000001-001,10,mM,sample",
      "A2,CC-000002-001,10,mM,sample",
      "H12,,,,positive_control",
    ];
    saveText([header, ...examples].join("\n"), "well_mapping_template.csv");
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
                setBatchId(well.batch_id ?? "");
                setConcValue(well.concentration_value?.toString() ?? "");
                setConcUnit(well.concentration_unit ?? "mM");
                setRole(well.well_type ?? "sample");
              } else {
                setBatchId("");
                setConcValue("");
                setRole("sample");
              }
            }}
          />

          {/* Right panel — tabs for click-assign vs CSV import */}
          <div className="w-80 shrink-0 border-l pl-4 overflow-auto">
            <Tabs defaultValue="click">
              <TabsList className="w-full">
                <TabsTrigger value="click" className="flex-1">
                  Click to Assign
                </TabsTrigger>
                <TabsTrigger value="csv" className="flex-1">
                  Paste / Upload CSV
                </TabsTrigger>
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
                          Currently:{" "}
                          {
                            WELL_TYPE_LABELS[
                              (wellMap[selectedWell].well_type ?? "sample") as WellType
                            ]
                          }
                          {wellMap[selectedWell].batch_id
                            ? ` · ${wellMap[selectedWell].batch_id}`
                            : ""}
                        </p>
                      )}
                    </div>
                    <div className="space-y-2">
                      <Label>Role</Label>
                      <Select value={role} onValueChange={setRole}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(WELL_TYPE_LABELS).map(([value, label]) => (
                            <SelectItem key={value} value={value}>
                              {label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>Batch</Label>
                      <BatchSearchPicker
                        value={batchId}
                        onSelect={setBatchId}
                        onClear={() => setBatchId("")}
                        onEnter={assignWell}
                      />
                      <p className="text-[11px] text-muted-foreground">
                        Leave empty for control / blank wells.
                      </p>
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
                        <Label>Unit</Label>
                        <Select value={concUnit} onValueChange={setConcUnit}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {CONCENTRATION_UNITS.map((u) => (
                              <SelectItem key={u} value={u}>
                                {u}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={assignWell}
                        disabled={!batchId.trim() && role === "sample"}
                      >
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
                    Paste CSV data or upload a file. Format:{" "}
                    <code className="text-xs bg-muted px-1 py-0.5 rounded">
                      Well, Batch#, Concentration, Unit, Role
                    </code>
                  </p>
                  <Textarea
                    placeholder={
                      "A1,CC-000001-001,10,mM,sample\nA2,CC-000002-001,10,mM,sample\nH12,,,,positive_control"
                    }
                    rows={8}
                    value={csvText}
                    onChange={(e) => setCsvText(e.target.value)}
                    className="font-mono text-xs"
                  />
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleCsvImport} disabled={!csvText.trim()}>
                    Apply Pasted Data
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => fileInputRef.current?.click()}>
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
