"use client";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Trash2 } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import type { ScaffoldCriterion, ScaffoldMode } from "../../types";

const MODE_OPTIONS: { value: ScaffoldMode; label: string }[] = [
  { value: "exact_match", label: "Exact match" },
  { value: "acyclic_only", label: "Acyclic only" },
];

export function ScaffoldCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: ScaffoldCriterion;
  onChange: (c: ScaffoldCriterion) => void;
  onRemove: () => void;
}) {
  function handleModeChange(next: ScaffoldMode) {
    if (next === "acyclic_only") {
      onChange({ type: "scaffold", mode: "acyclic_only" });
    } else {
      onChange({
        type: "scaffold",
        mode: "exact_match",
        scaffold_smiles: criterion.scaffold_smiles ?? "",
      });
    }
  }

  return (
    <div className="flex items-end gap-2 flex-wrap">
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Mode</Label>
        <div role="group" aria-label="Scaffold mode" className="inline-flex rounded-md border bg-background p-0.5">
          {MODE_OPTIONS.map((opt) => (
            <Button
              key={opt.value}
              type="button"
              variant={criterion.mode === opt.value ? "default" : "ghost"}
              size="sm"
              className={cn(
                "h-7 px-3 text-xs",
                criterion.mode === opt.value && "shadow-sm",
              )}
              onClick={() => handleModeChange(opt.value)}
            >
              {opt.label}
            </Button>
          ))}
        </div>
      </div>

      {criterion.mode === "exact_match" && (
        <div className="flex-1 min-w-64">
          <Label className="text-xs text-muted-foreground">Scaffold SMILES</Label>
          <Input
            className="h-9 font-mono text-xs"
            placeholder="Scaffold SMILES (e.g. c1ccc2ncccc2c1)"
            value={criterion.scaffold_smiles ?? ""}
            onChange={(e) =>
              onChange({
                type: "scaffold",
                mode: "exact_match",
                scaffold_smiles: e.target.value.trim(),
              })
            }
          />
        </div>
      )}

      <div className="flex-1" />
      <Button
        variant="ghost"
        size="icon"
        className="h-9 w-9 shrink-0"
        onClick={onRemove}
        aria-label="Remove criterion"
      >
        <Trash2 className="h-4 w-4 text-muted-foreground" />
      </Button>
    </div>
  );
}
