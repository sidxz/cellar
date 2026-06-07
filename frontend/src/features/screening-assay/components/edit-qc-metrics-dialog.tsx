"use client";

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
import { Plus, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";
import { useUpdateRun } from "../hooks/use-runs";
import type { Run } from "../types";

interface EditQcMetricsDialogProps {
  run: Run;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface MetricRow {
  /** Stable client id so React keys the row by identity, not array index —
   *  keeps focus / uncommitted text attached to the right row across add /
   *  remove. Never sent to the server (stripped by `rowsToMetrics`). */
  _id: string;
  key: string;
  value: string;
}

const QC_PRESETS = [
  { value: "z_prime", label: "Z' Factor" },
  { value: "signal_to_noise", label: "Signal to Noise" },
  { value: "cv_percent", label: "CV %" },
  { value: "signal_to_background", label: "Signal to Background" },
  { value: "z_factor", label: "Z Factor" },
] as const;

function metricsToRows(qcMetrics: Record<string, unknown> | null): MetricRow[] {
  if (!qcMetrics || Object.keys(qcMetrics).length === 0) {
    return [];
  }
  return Object.entries(qcMetrics).map(([key, value]) => ({
    _id: crypto.randomUUID(),
    key,
    value: String(value ?? ""),
  }));
}

function rowsToMetrics(rows: MetricRow[]): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const row of rows) {
    const trimmedKey = row.key.trim();
    if (!trimmedKey) continue;
    const numVal = Number(row.value);
    result[trimmedKey] = Number.isNaN(numVal) ? row.value : numVal;
  }
  return result;
}

export function EditQcMetricsDialog({ run, open, onOpenChange }: EditQcMetricsDialogProps) {
  const updateRun = useUpdateRun();

  const [rows, setRows] = useState<MetricRow[]>(() => metricsToRows(run.qc_metrics));

  const resetForm = useCallback(() => {
    setRows(metricsToRows(run.qc_metrics));
  }, [run.qc_metrics]);

  const handleAddRow = () => {
    setRows((prev) => [...prev, { _id: crypto.randomUUID(), key: "", value: "" }]);
  };

  const handleRemoveRow = (index: number) => {
    setRows((prev) => prev.filter((_, i) => i !== index));
  };

  const handleKeyChange = (index: number, newKey: string) => {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, key: newKey } : row)));
  };

  const handleValueChange = (index: number, newValue: string) => {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, value: newValue } : row)));
  };

  const handleAddPreset = (preset: string) => {
    const exists = rows.some((r) => r.key === preset);
    if (!exists) {
      setRows((prev) => [...prev, { _id: crypto.randomUUID(), key: preset, value: "" }]);
    }
  };

  const handleSubmit = () => {
    const metrics = rowsToMetrics(rows);
    updateRun.mutate(
      {
        runId: run.id,
        data: {
          qc_metrics: Object.keys(metrics).length > 0 ? metrics : null,
        },
      },
      {
        onSuccess: () => {
          onOpenChange(false);
        },
      },
    );
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (nextOpen) {
      resetForm();
    }
    onOpenChange(nextOpen);
  };

  const existingKeys = new Set(rows.map((r) => r.key));
  const availablePresets = QC_PRESETS.filter((p) => !existingKeys.has(p.value));

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit QC Metrics</DialogTitle>
          <DialogDescription>Add or modify quality control metrics for this run.</DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* Preset dropdown */}
          {availablePresets.length > 0 && (
            <div className="grid gap-2">
              <Label>Add Common Metric</Label>
              <Select onValueChange={handleAddPreset}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a preset..." />
                </SelectTrigger>
                <SelectContent>
                  {availablePresets.map((preset) => (
                    <SelectItem key={preset.value} value={preset.value}>
                      {preset.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Metric rows */}
          <div className="grid gap-2">
            <Label>Metrics</Label>
            {rows.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No metrics defined. Add a preset above or click &quot;Add Metric&quot; below.
              </p>
            )}
            {rows.map((row, index) => (
              <div key={row._id} className="flex items-center gap-2">
                <Input
                  placeholder="Key"
                  value={row.key}
                  onChange={(e) => handleKeyChange(index, e.target.value)}
                  className="flex-1"
                />
                <Input
                  placeholder="Value"
                  value={row.value}
                  onChange={(e) => handleValueChange(index, e.target.value)}
                  className="flex-1"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => handleRemoveRow(index)}
                >
                  <Trash2 className="h-4 w-4 text-muted-foreground" />
                </Button>
              </div>
            ))}
          </div>

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleAddRow}
            className="w-fit"
          >
            <Plus className="mr-2 h-4 w-4" />
            Add Metric
          </Button>
        </div>

        <DialogFooter>
          <Button onClick={handleSubmit} disabled={updateRun.isPending}>
            {updateRun.isPending ? "Saving..." : "Save Metrics"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
