"use client";

import { StructureEditorDialog, StructureRenderer } from "@/shared/components/chemistry";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Pencil } from "lucide-react";
import { useState } from "react";
import { useSearchAlgorithms } from "../../hooks/use-search-algorithms";
import type { SearchMode, StructureCriterion, StructureSearchType } from "../../types";

// ─── Constants ──────────────────────────────────────────────────────────────

const SEARCH_TYPES: { value: StructureSearchType; label: string }[] = [
  { value: "substructure", label: "substructure" },
  { value: "exact", label: "exact" },
  { value: "similarity", label: "similarity" },
];

const PLACEHOLDERS: Record<StructureSearchType, string> = {
  substructure: "e.g. c1ccccc1",
  exact: "InChI Key, e.g. BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
  similarity: "e.g. CCO",
};

// Fallback mode metadata if the /search/algorithms call hasn't returned yet.
const FALLBACK_MODES: {
  name: SearchMode;
  label: string;
  description: string;
  default_threshold: number;
}[] = [
  {
    name: "similar",
    label: "Similar",
    description: "Find molecules with the same overall shape",
    default_threshold: 0.7,
  },
  {
    name: "scaffold_hop",
    label: "Scaffold hop",
    description: "Looser match — bioisosteric replacements",
    default_threshold: 0.55,
  },
  {
    name: "fragment_in_target",
    label: "Contains my fragment",
    description: "Big molecules that contain features of this query",
    default_threshold: 0.7,
  },
];

function defaultStructureCriterion(): StructureCriterion {
  return {
    type: "structure",
    search_type: "substructure",
    kind: "substructure",
    smarts: "",
    smiles: undefined,
    smiles_or_smarts: undefined,
    threshold: 0.7,
    inchi_key: undefined,
    mode: undefined,
    generalized: false,
  };
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getInputValue(c: StructureCriterion): string {
  if (c.search_type === "substructure") return c.smiles_or_smarts ?? c.smarts ?? "";
  if (c.search_type === "similarity") return c.smiles ?? "";
  return c.inchi_key ?? "";
}

function setInputValue(c: StructureCriterion, value: string): StructureCriterion {
  if (c.search_type === "substructure") {
    // Mirror to both fields for safety with downstream consumers.
    return { ...c, smiles_or_smarts: value, smarts: value };
  }
  if (c.search_type === "similarity") return { ...c, smiles: value };
  return { ...c, inchi_key: value };
}

function getPreviewSmiles(c: StructureCriterion): string | undefined {
  if (c.search_type === "substructure") {
    const v = c.smiles_or_smarts ?? c.smarts;
    return v || undefined;
  }
  if (c.search_type === "similarity") return c.smiles || undefined;
  return undefined;
}

function hasValue(c: StructureCriterion): boolean {
  if (c.search_type === "substructure") {
    return ((c.smiles_or_smarts ?? c.smarts)?.length ?? 0) > 0;
  }
  if (c.search_type === "similarity") return (c.smiles?.length ?? 0) > 0;
  return (c.inchi_key?.length ?? 0) > 0;
}

// ─── Section ─────────────────────────────────────────────────────────────────

interface StructureSectionProps {
  criterion: StructureCriterion | null;
  onChange: (criterion: StructureCriterion | null) => void;
}

export function StructureSection({ criterion, onChange }: StructureSectionProps) {
  const [editorOpen, setEditorOpen] = useState(false);
  const { data: algorithmsData } = useSearchAlgorithms();
  const modes = algorithmsData?.modes ?? FALLBACK_MODES;

  const c = criterion ?? defaultStructureCriterion();
  const currentMode = c.mode ?? "similar";
  const previewSmiles = getPreviewSmiles(c);
  const inputValue = getInputValue(c);
  const isStructureMode = c.search_type !== "exact";
  const editorOutputFormat = c.search_type === "substructure" ? "smarts" : "smiles";
  const filled = hasValue(c);

  function handleTypeChange(type: StructureSearchType) {
    const base: StructureCriterion = {
      ...defaultStructureCriterion(),
      search_type: type,
      kind: type,
    };
    if (type === "similarity") {
      base.mode = "similar";
      base.threshold = modes.find((m) => m.name === "similar")?.default_threshold ?? 0.7;
    }
    onChange(base);
  }

  function handleModeChange(mode: SearchMode) {
    const m = modes.find((x) => x.name === mode);
    onChange({ ...c, mode, threshold: m?.default_threshold ?? c.threshold ?? 0.7 });
  }

  function handleInputChange(value: string) {
    onChange(setInputValue(c, value));
  }

  function handleEditorApply(structure: string) {
    onChange(setInputValue(c, structure));
  }

  function handleThresholdChange(value: string) {
    const pct = Math.min(100, Math.max(0, Number.parseInt(value, 10) || 0));
    onChange({ ...c, threshold: pct / 100 });
  }

  function handleGeneralizedToggle(checked: boolean) {
    onChange({ ...c, generalized: checked });
  }

  function handleClear() {
    onChange(null);
  }

  return (
    <div className="space-y-2">
      {/* Header row */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Structure
        </span>
        {filled && (
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded-full border border-destructive/20 bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive hover:bg-destructive/20 transition-colors"
            onClick={handleClear}
          >
            Clear
          </button>
        )}
      </div>

      {/* Radio row: type selectors + inline threshold */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {SEARCH_TYPES.map((st) => {
          const active = c.search_type === st.value;
          return (
            <label
              key={st.value}
              className={`flex cursor-pointer items-center gap-1 text-sm select-none ${
                active ? "text-foreground" : "text-muted-foreground"
              }`}
            >
              <input
                type="radio"
                name="structure-search-type"
                value={st.value}
                checked={active}
                onChange={() => handleTypeChange(st.value)}
                className="accent-primary"
              />
              {st.label}
              {/* Inline threshold for similarity */}
              {st.value === "similarity" && active && (
                <span className="flex items-center gap-0.5 ml-1">
                  <span className="text-muted-foreground">≥</span>
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    step={5}
                    value={Math.round((c.threshold ?? 0.7) * 100)}
                    onChange={(e) => handleThresholdChange(e.target.value)}
                    className="h-6 w-14 text-sm text-center"
                    onClick={(e) => e.stopPropagation()}
                  />
                  <span className="text-muted-foreground">%</span>
                </span>
              )}
            </label>
          );
        })}
      </div>

      {/* Mode radios for similarity */}
      {c.search_type === "similarity" && (
        <div className="space-y-1 pl-1">
          {modes.map((m) => {
            const active = currentMode === m.name;
            return (
              <label
                key={m.name}
                className={`flex cursor-pointer items-start gap-2 text-sm select-none ${
                  active ? "text-foreground" : "text-muted-foreground"
                }`}
              >
                <input
                  type="radio"
                  name="similarity-mode"
                  value={m.name}
                  checked={active}
                  onChange={() => handleModeChange(m.name as SearchMode)}
                  className="mt-0.5 accent-primary"
                />
                <span>
                  <span className="font-medium">{m.label}</span>
                  <span className="ml-2 text-xs text-muted-foreground">{m.description}</span>
                </span>
              </label>
            );
          })}
        </div>
      )}

      {/* Generalized substructure toggle */}
      {c.search_type === "substructure" && (
        <label className="flex cursor-pointer items-center gap-2 text-sm select-none pl-1">
          <input
            type="checkbox"
            checked={c.generalized ?? false}
            onChange={(e) => handleGeneralizedToggle(e.target.checked)}
            className="accent-primary"
          />
          <span>
            Allow tautomer / link-node matches
            <span className="ml-2 text-xs text-muted-foreground">
              (uses <code>@&gt;&gt;</code> with <code>mol_to_xqmol</code>)
            </span>
          </span>
        </label>
      )}

      {/* Structure preview */}
      {previewSmiles && previewSmiles.length >= 2 && (
        <div className="flex justify-center rounded border border-border bg-muted/30 p-2">
          <StructureRenderer smiles={previewSmiles} width={120} height={90} />
        </div>
      )}

      {/* Input row */}
      <div className="flex items-center gap-1">
        <Input
          className="h-8 flex-1 text-sm font-mono"
          placeholder={PLACEHOLDERS[c.search_type]}
          value={inputValue}
          onChange={(e) => handleInputChange(e.target.value)}
        />
        {isStructureMode && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 w-7 p-0"
            onClick={() => setEditorOpen(true)}
            title="Draw structure"
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      {/* Structure editor dialog */}
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
