"use client";

import { useCallback, useEffect, useState } from "react";
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

// ---------------------------------------------------------------------------
// Component
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

  // Local editable copy of well_map
  const [wellMap, setWellMap] = useState<Record<string, WellMapping>>({});
  const [selectedWell, setSelectedWell] = useState<string | null>(null);
  const [batchId, setBatchId] = useState("");
  const [concValue, setConcValue] = useState("");
  const [concUnit, setConcUnit] = useState("mM");

  useEffect(() => {
    if (open) {
      setWellMap(initialWellMap ? { ...initialWellMap } : {});
      setSelectedWell(null);
      setBatchId("");
      setConcValue("");
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

  const handleSave = () => {
    mapWells.mutate(wellMap, {
      onSuccess: () => onOpenChange(false),
    });
  };

  const mappedCount = Object.keys(wellMap).length;
  const fmt = parseInt(format, 10);
  const cellSize =
    fmt > 384
      ? "h-4 w-4 text-[5px]"
      : fmt > 96
        ? "h-6 w-6 text-[8px]"
        : "h-9 w-9 text-xs";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[95vw] w-[1200px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Map Wells to Batches</DialogTitle>
          <DialogDescription>
            Click a well to select it, then enter a batch number and concentration.
            {mappedCount > 0 && ` (${mappedCount} wells mapped)`}
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-[1fr_280px] gap-6">
          {/* Plate grid */}
          <div className="overflow-auto">
            <div className="inline-flex flex-col gap-0.5">
              {/* Column headers */}
              <div className="flex gap-0.5 pl-6">
                {Array.from({ length: cols }, (_, i) => (
                  <div
                    key={i}
                    className={`${cellSize} flex items-center justify-center text-muted-foreground font-mono`}
                  >
                    {i + 1}
                  </div>
                ))}
              </div>
              {letters.map((row) => (
                <div key={row} className="flex gap-0.5">
                  <div className={`w-5 flex items-center justify-center text-xs text-muted-foreground font-mono`}>
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
                        onClick={() => {
                          setSelectedWell(pos);
                          if (well) {
                            setBatchId(well.batch_id);
                            setConcValue(
                              well.concentration_value?.toString() ?? ""
                            );
                            setConcUnit(well.concentration_unit ?? "mM");
                          } else {
                            setBatchId("");
                            setConcValue("");
                          }
                        }}
                        title={
                          well
                            ? `${pos}: ${well.batch_id} @ ${well.concentration_value ?? "—"} ${well.concentration_unit ?? ""}`
                            : pos
                        }
                        className={`${cellSize} rounded-sm border transition-colors flex items-center justify-center font-mono
                          ${isSelected ? "ring-2 ring-primary border-primary" : ""}
                          ${well ? "bg-primary/60 border-primary/40 text-primary-foreground" : "bg-muted/30 border-muted hover:bg-muted/60"}
                        `}
                      />
                    );
                  })}
                </div>
              ))}
            </div>
          </div>

          {/* Assignment panel */}
          <div className="space-y-4 border-l pl-4">
            {selectedWell ? (
              <>
                <div>
                  <p className="text-sm font-medium">
                    Well <span className="font-mono text-primary">{selectedWell}</span>
                  </p>
                  {wellMap[selectedWell] && (
                    <p className="text-xs text-muted-foreground mt-1">
                      Currently: {wellMap[selectedWell].batch_id}
                    </p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="batch-id">Batch # or ID</Label>
                  <Input
                    id="batch-id"
                    placeholder="e.g. CV-00001-001"
                    value={batchId}
                    onChange={(e) => setBatchId(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") assignWell();
                    }}
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
                    Assign
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
              <p className="text-sm text-muted-foreground">
                Click a well on the plate to assign a batch.
              </p>
            )}
          </div>
        </div>

        <DialogFooter>
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
