"use client";

import { StructureEditorDialog, StructureRenderer } from "@/shared/components/chemistry";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { cn } from "@/shared/lib/utils";
import { Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
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
  const [editorOpen, setEditorOpen] = useState(false);

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

  function handleEditorApply(structure: string) {
    onChange({
      type: "scaffold",
      mode: "exact_match",
      scaffold_smiles: structure.trim(),
    });
  }

  const smiles = criterion.mode === "exact_match" ? (criterion.scaffold_smiles ?? "") : "";
  const hasStructure = smiles.length >= 2;

  return (
    <div className="space-y-2">
      <div className="flex items-end gap-2 flex-wrap">
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Mode</Label>
          <div
            role="group"
            aria-label="Scaffold mode"
            className="inline-flex rounded-md border bg-background p-0.5"
          >
            {MODE_OPTIONS.map((opt) => (
              <Button
                key={opt.value}
                type="button"
                variant={criterion.mode === opt.value ? "default" : "ghost"}
                size="sm"
                className={cn("h-7 px-3 text-xs", criterion.mode === opt.value && "shadow-sm")}
                onClick={() => handleModeChange(opt.value)}
              >
                {opt.label}
              </Button>
            ))}
          </div>
        </div>

        {criterion.mode === "exact_match" && (
          <div className="flex-1 min-w-64 flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">Scaffold SMILES</Label>
            <div className="flex items-center gap-1.5">
              <Input
                className="h-9 flex-1 font-mono text-xs"
                placeholder="Scaffold SMILES (e.g. c1ccc2ncccc2c1)"
                value={smiles}
                onChange={(e) =>
                  onChange({
                    type: "scaffold",
                    mode: "exact_match",
                    scaffold_smiles: e.target.value.trim(),
                  })
                }
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-9 px-2.5 gap-1.5 shrink-0"
                onClick={() => setEditorOpen(true)}
                title="Draw scaffold with Ketcher"
              >
                <Pencil className="h-3.5 w-3.5" />
                <span>{hasStructure ? "Edit" : "Draw"}</span>
              </Button>
            </div>
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

      {/* Structure preview — appears centered below the row when there's a
          SMILES to render. The BE strips decorated molecules to their
          Bemis-Murcko scaffold before comparing, so this preview shows
          chemists what they typed/drew, not what the BE will match. */}
      {criterion.mode === "exact_match" && hasStructure && (
        <div className="flex justify-center rounded border border-border bg-muted/30 p-2">
          <StructureRenderer smiles={smiles} width={120} height={90} />
        </div>
      )}

      {criterion.mode === "exact_match" && (
        <StructureEditorDialog
          open={editorOpen}
          onOpenChange={setEditorOpen}
          initialStructure={smiles}
          onApply={handleEditorApply}
          outputFormat="smiles"
        />
      )}
    </div>
  );
}
