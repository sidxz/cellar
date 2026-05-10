"use client";

import { StructureEditorDialog, StructureRenderer } from "@/shared/components/chemistry";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { detectQueryKind } from "@/shared/lib/rdkit/detect-query-kind";
import { Pencil } from "lucide-react";
import { useState } from "react";
import { useSearchAlgorithms } from "../../hooks/use-search-algorithms";
import type { SearchMode, StructureCriterion, StructureSearchType } from "../../types";

// ─── Constants ──────────────────────────────────────────────────────────────

// Order chosen by chemist-frequency on the discovery search panel:
// substructure (daily SAR / scaffold filtering) → similarity (lead-hopping,
// analog finding) → exact (rare lookup; mostly a registration / IP-dedup
// concern, which has its own dedicated UIs). Tab order follows likelihood.
const SEARCH_TYPES: { value: StructureSearchType; label: string }[] = [
  { value: "substructure", label: "substructure" },
  { value: "similarity", label: "similarity" },
  { value: "exact", label: "exact" },
];

const PLACEHOLDERS: Record<StructureSearchType, string> = {
  substructure: "e.g. c1ccccc1",
  exact: "InChI Key, e.g. BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
  similarity: "e.g. CCO",
};

// Fallback mode metadata if the /search/algorithms call hasn't returned yet.
// Keep these in sync with the backend MODE_DEFAULTS in
// `domain/sar_analysis/search_modes.py`.
const FALLBACK_MODES: {
  name: SearchMode;
  label: string;
  description: string;
  default_threshold: number;
}[] = [
  {
    name: "similar",
    label: "Similar",
    description: "Tanimoto similarity over Morgan/ECFP4 fingerprints.",
    default_threshold: 0.7,
  },
  {
    name: "scaffold_hop",
    label: "Scaffold hop",
    description:
      "Tanimoto over feature-class (FCFP4) fingerprints. Surfaces bioisosteric replacements that strict similarity may miss.",
    default_threshold: 0.55,
  },
  {
    name: "fragment_in_target",
    label: "Contains my fragment",
    description:
      "Asymmetric Tversky similarity (α=1, β=0). Ranks targets by the fraction of query features they contain.",
    default_threshold: 0.7,
  },
];

function defaultStructureCriterion(): StructureCriterion {
  return {
    type: "structure",
    search_type: "substructure",
    kind: "substructure",
    smiles_or_smarts: undefined,
    smiles: undefined,
    threshold: 0.7,
    inchi_key: undefined,
    mode: undefined,
    generalized: false,
    query_kind: undefined,
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
    // Auto-detect SMILES vs SMARTS for typed input. Drawing-derived
    // input arrives via handleEditorApply with an explicit query_kind.
    return {
      ...c,
      smiles_or_smarts: value,
      query_kind: value ? detectQueryKind(value) : undefined,
    };
  }
  if (c.search_type === "similarity") return { ...c, smiles: value };
  return { ...c, inchi_key: value };
}

function setStructureFromEditor(
  c: StructureCriterion,
  value: string,
  format: "smiles" | "smarts",
): StructureCriterion {
  if (c.search_type !== "substructure") {
    // Editor only emits SMILES for similarity/exact today; preserve.
    return setInputValue(c, value);
  }
  return {
    ...c,
    smiles_or_smarts: value,
    query_kind: format,
    // Generalized matching only makes sense with structural (SMILES)
    // queries. Auto-clear if Ketcher dropped us into SMARTS mode.
    generalized: format === "smarts" ? false : c.generalized,
  };
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
  const editorOutputFormat: "smiles" | "smarts" | "auto" =
    c.search_type === "substructure" ? "auto" : "smiles";
  const filled = hasValue(c);
  const isSmartsMode = c.search_type === "substructure" && c.query_kind === "smarts";

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

  function handleEditorApply(structure: string, format: "smiles" | "smarts") {
    onChange(setStructureFromEditor(c, structure, format));
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
                    // Right-align + slight right padding so digits clear the
                    // browser-rendered spinner caret. w-[4.5rem] fits 3-digit
                    // values (e.g. 100) plus the spinner without clipping.
                    className="h-6 w-[4.5rem] text-sm text-right pr-1"
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

      {/* Generalized substructure toggle. Disabled in SMARTS mode —
          tautomer/variant expansion needs a structural query and the
          cartridge can't apply it to atom lists / R-groups / "any
          bond" patterns. */}
      {c.search_type === "substructure" && (
        <label
          className={`flex items-center gap-2 text-sm select-none pl-1 ${
            isSmartsMode ? "cursor-not-allowed text-muted-foreground" : "cursor-pointer"
          }`}
          title={
            isSmartsMode
              ? "Tautomer matching needs a structural query — atom lists, R-groups and special markers don't apply here"
              : undefined
          }
        >
          <input
            type="checkbox"
            checked={!isSmartsMode && (c.generalized ?? false)}
            disabled={isSmartsMode}
            onChange={(e) => handleGeneralizedToggle(e.target.checked)}
            className="accent-primary"
          />
          <span>Match across tautomers and structural variants</span>
        </label>
      )}

      {/* Structure preview */}
      {previewSmiles && previewSmiles.length >= 2 && (
        <div className="flex justify-center rounded border border-border bg-muted/30 p-2">
          <StructureRenderer smiles={previewSmiles} width={120} height={90} />
        </div>
      )}

      {/* Input row — type SMILES/SMARTS, or click "Draw structure" to open Ketcher.
          The button is labeled (not a bare pencil) so chemists who came from
          ChemDraw / Ketcher / MarvinSketch see the path immediately without
          parsing an icon. */}
      <div className="flex items-center gap-1.5">
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
            className="h-8 px-2.5 gap-1.5 shrink-0"
            onClick={() => setEditorOpen(true)}
            title="Draw structure with Ketcher"
          >
            <Pencil className="h-3.5 w-3.5" />
            <span>{filled ? "Edit structure" : "Draw structure"}</span>
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
