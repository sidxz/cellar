"use client";

import { useState } from "react";
import { Pencil, X } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { StructureRenderer, StructureEditorDialog } from "@/shared/components/chemistry";
import type { StructureCriterion, StructureSearchType } from "../../types";

// ─── Constants ──────────────────────────────────────────────────────────────

const STRUCTURE_TYPES: { value: StructureSearchType; label: string }[] = [
  { value: "substructure", label: "Substructure (SMARTS)" },
  { value: "similarity", label: "Similarity (SMILES)" },
  { value: "exact", label: "Exact (InChIKey)" },
];

function defaultStructureCriterion(): StructureCriterion {
  return { type: "structure", search_type: "substructure", smarts: "", smiles: undefined, threshold: 0.7, inchi_key: undefined };
}

// ─── Section ────────────────────────────────────────────────────────────────

interface StructureSectionProps {
  criterion: StructureCriterion | null;
  onChange: (criterion: StructureCriterion | null) => void;
}

export function StructureSection({ criterion, onChange }: StructureSectionProps) {
  const [editorOpen, setEditorOpen] = useState(false);

  // Initialize if user starts interacting and there's no criterion
  const c = criterion ?? defaultStructureCriterion();

  const previewSmiles =
    c.search_type === "substructure"
      ? c.smarts
      : c.search_type === "similarity"
        ? c.smiles
        : undefined;

  const isStructureMode =
    c.search_type === "substructure" || c.search_type === "similarity";

  const editorOutputFormat =
    c.search_type === "substructure" ? "smarts" : "smiles";

  function handleEditorApply(structure: string) {
    if (c.search_type === "substructure") {
      onChange({ ...c, smarts: structure });
    } else {
      onChange({ ...c, smiles: structure });
    }
  }

  function handleClear() {
    onChange(null);
  }

  function handleTypeChange(v: string) {
    onChange({ ...defaultStructureCriterion(), search_type: v as StructureSearchType });
  }

  const hasValue =
    (c.search_type === "substructure" && c.smarts && c.smarts.length > 0) ||
    (c.search_type === "similarity" && c.smiles && c.smiles.length > 0) ||
    (c.search_type === "exact" && c.inchi_key && c.inchi_key.length > 0);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-sm font-medium">Structure Search</Label>
        {hasValue && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-muted-foreground"
            onClick={handleClear}
          >
            <X className="mr-1 h-3 w-3" />
            Clear
          </Button>
        )}
      </div>

      <div className="flex items-start gap-3">
        {/* Structure preview */}
        {previewSmiles && previewSmiles.length >= 2 && (
          <div className="shrink-0 rounded border border-border bg-muted/30 p-1">
            <StructureRenderer smiles={previewSmiles} width={100} height={80} />
          </div>
        )}

        <div className="flex flex-1 flex-wrap items-end gap-2">
          <div className="w-48">
            <Label className="text-xs text-muted-foreground">Search Type</Label>
            <Select value={c.search_type} onValueChange={handleTypeChange}>
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STRUCTURE_TYPES.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {c.search_type === "substructure" && (
            <div className="flex-1 min-w-[200px]">
              <Label className="text-xs text-muted-foreground">SMARTS</Label>
              <div className="flex gap-1">
                <Input
                  className="h-9 font-mono text-xs"
                  placeholder="e.g. c1ccccc1"
                  value={c.smarts ?? ""}
                  onChange={(e) => onChange({ ...c, smarts: e.target.value })}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="h-9 w-9 shrink-0"
                  onClick={() => setEditorOpen(true)}
                  title="Draw structure"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          )}

          {c.search_type === "similarity" && (
            <>
              <div className="flex-1 min-w-[200px]">
                <Label className="text-xs text-muted-foreground">SMILES</Label>
                <div className="flex gap-1">
                  <Input
                    className="h-9 font-mono text-xs"
                    placeholder="e.g. CCO"
                    value={c.smiles ?? ""}
                    onChange={(e) => onChange({ ...c, smiles: e.target.value })}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    className="h-9 w-9 shrink-0"
                    onClick={() => setEditorOpen(true)}
                    title="Draw structure"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
              <div className="w-32">
                <Label className="text-xs text-muted-foreground">
                  Threshold ({c.threshold?.toFixed(2) ?? "0.70"})
                </Label>
                <Input
                  className="h-9"
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={c.threshold ?? 0.7}
                  onChange={(e) => onChange({ ...c, threshold: Number(e.target.value) })}
                />
              </div>
            </>
          )}

          {c.search_type === "exact" && (
            <div className="flex-1 min-w-[200px]">
              <Label className="text-xs text-muted-foreground">InChI Key</Label>
              <Input
                className="h-9 font-mono text-xs"
                placeholder="e.g. BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
                value={c.inchi_key ?? ""}
                onChange={(e) => onChange({ ...c, inchi_key: e.target.value })}
              />
            </div>
          )}
        </div>
      </div>

      {isStructureMode && (
        <StructureEditorDialog
          open={editorOpen}
          onOpenChange={setEditorOpen}
          initialStructure={previewSmiles ?? ""}
          onApply={handleEditorApply}
          outputFormat={editorOutputFormat}
        />
      )}
    </div>
  );
}
