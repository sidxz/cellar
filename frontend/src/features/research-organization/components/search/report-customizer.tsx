"use client";

import type { Protocol } from "@/features/screening-assay/types";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible";
import { Label } from "@/shared/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import { Separator } from "@/shared/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/shared/components/ui/sheet";
import { Switch } from "@/shared/components/ui/switch";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useReportConfig } from "../../hooks/use-report-config";
import { expandParentTokens } from "../../lib/protocol-column-id";
import {
  buildReadoutCustomizerEntries,
  replaceProtocolEntries,
} from "../../lib/readout-customizer-entries";
import type { DetailLevel, ImageSize, PlotScale } from "../../types";

// ─── Field definitions ──────────────────────────────────────────────────────

const STRUCTURE_FIELDS = [
  { key: "structure", label: "Structure" },
  { key: "registration_number", label: "Reg#" },
  { key: "smiles", label: "SMILES" },
  { key: "inchi", label: "InChI" },
  { key: "inchi_key", label: "InChIKey" },
  { key: "iupac_name", label: "IUPAC Name" },
] as const;

const PROPERTY_FIELDS = [
  { key: "molecular_weight", label: "MW" },
  { key: "logp", label: "LogP" },
  { key: "tpsa", label: "TPSA" },
  { key: "hbd", label: "HBD" },
  { key: "hba", label: "HBA" },
  { key: "rotatable_bonds", label: "Rotatable Bonds" },
  { key: "heavy_atoms", label: "Heavy Atoms" },
  { key: "aromatic_rings", label: "Aromatic Rings" },
  { key: "ring_count", label: "Ring Count" },
  { key: "ro5_violations", label: "Ro5 Violations" },
  { key: "formula", label: "Formula" },
] as const;

const MOLECULE_FIELDS = [
  { key: "name", label: "Name" },
  { key: "lifecycle_stage", label: "Lifecycle Stage" },
  { key: "structure_status", label: "Structure Status" },
  { key: "molecule_type", label: "Type" },
  { key: "created_at", label: "Created Date" },
] as const;

const BATCH_FIELDS = [
  { key: "batch_number", label: "Batch Number" },
  { key: "source", label: "Source" },
  { key: "purity", label: "Purity" },
  { key: "salt_form", label: "Salt Form" },
  { key: "vendor", label: "Vendor" },
  { key: "amount", label: "Amount" },
] as const;

const PROTOCOL_FIELDS = [
  { key: "fitted_value", label: "Fitted Value" },
  { key: "plot", label: "Plot" },
  { key: "r_squared", label: "R\u00B2" },
  { key: "hill_slope", label: "Hill Slope" },
  { key: "n", label: "N" },
  { key: "curve_class", label: "Curve Class" },
  { key: "ci_lower", label: "CI Lower" },
  { key: "ci_upper", label: "CI Upper" },
  { key: "top_pct", label: "Top%" },
  { key: "bottom_pct", label: "Bottom%" },
] as const;

// ─── Props ──────────────────────────────────────────────────────────────────

interface ReportCustomizerProps {
  open: boolean;
  onClose: () => void;
  onUpdate: () => void;
  protocols: Protocol[];
  activeProtocolIds: string[];
  /** Current set of column-id tokens the grid is rendering. Drives the
   *  check-state of the Readouts groups so checks always reflect what's
   *  actually on screen — no separate shadow state. */
  protocolColumns: string[];
  /** Toggle handler — caller updates the search reducer so the grid
   *  re-renders with the new column set. */
  onProtocolColumnsChange: (next: string[]) => void;
}

// ─── Component ──────────────────────────────────────────────────────────────

export function ReportCustomizer({
  open,
  onClose,
  onUpdate,
  protocols,
  activeProtocolIds,
  protocolColumns,
  onProtocolColumnsChange,
}: ReportCustomizerProps) {
  const { config, updateConfig, setVisibleFields, setProtocolFields } = useReportConfig();
  const { visibleFields } = config;

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent side="right" className="w-[420px] sm:max-w-[420px] p-0 flex flex-col">
        <SheetHeader className="px-4 pt-4 pb-2 shrink-0">
          <SheetTitle>Customize Report</SheetTitle>
          <SheetDescription>
            Configure which fields and display options appear in search results.
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1 min-h-0 px-4 pb-6">
          <div className="space-y-6 pb-8">
            {/* ── Display Options ── */}
            <section className="space-y-4">
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                Display Options
              </h3>

              {/* Detail Level */}
              <div className="space-y-2">
                <Label className="text-sm font-medium">Detail Level</Label>
                <RadioGroup
                  value={config.detailLevel}
                  onValueChange={(v) => updateConfig({ detailLevel: v as DetailLevel })}
                  className="grid gap-2"
                >
                  <div className="flex items-center gap-2">
                    <RadioGroupItem value="summary" id="detail-summary" />
                    <Label htmlFor="detail-summary" className="cursor-pointer">
                      Summary
                    </Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <RadioGroupItem value="run_batch" id="detail-run-batch" disabled />
                    <Label
                      htmlFor="detail-run-batch"
                      className="cursor-not-allowed text-muted-foreground"
                    >
                      Run/Batch <span className="text-xs italic">(v2)</span>
                    </Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <RadioGroupItem value="details" id="detail-details" disabled />
                    <Label
                      htmlFor="detail-details"
                      className="cursor-not-allowed text-muted-foreground"
                    >
                      Details <span className="text-xs italic">(v2)</span>
                    </Label>
                  </div>
                </RadioGroup>
              </div>

              {/* Plot Scale */}
              <div className="space-y-2">
                <Label className="text-sm font-medium">Plot Scale</Label>
                <RadioGroup
                  value={config.plotScale}
                  onValueChange={(v) => updateConfig({ plotScale: v as PlotScale })}
                  className="grid gap-2"
                >
                  <div className="flex items-center gap-2">
                    <RadioGroupItem value="per_molecule" id="scale-molecule" />
                    <Label htmlFor="scale-molecule" className="cursor-pointer">
                      Per Molecule
                    </Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <RadioGroupItem value="min_max" id="scale-minmax" />
                    <Label htmlFor="scale-minmax" className="cursor-pointer">
                      Min/Max of Results
                    </Label>
                  </div>
                </RadioGroup>
              </div>

              {/* Show Plot Legend */}
              <div className="flex items-center justify-between">
                <Label className="text-sm font-medium">Show Plot Legend</Label>
                <Switch
                  checked={config.showPlotLegend}
                  onCheckedChange={(v) => updateConfig({ showPlotLegend: v })}
                />
              </div>

              {/* Structure Image Size */}
              <div className="space-y-2">
                <Label className="text-sm font-medium">Structure Image Size</Label>
                <RadioGroup
                  value={config.imageSize}
                  onValueChange={(v) => updateConfig({ imageSize: v as ImageSize })}
                  className="flex gap-4"
                >
                  <div className="flex items-center gap-2">
                    <RadioGroupItem value="small" id="img-small" />
                    <Label htmlFor="img-small" className="cursor-pointer">
                      Small
                    </Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <RadioGroupItem value="medium" id="img-medium" />
                    <Label htmlFor="img-medium" className="cursor-pointer">
                      Medium
                    </Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <RadioGroupItem value="large" id="img-large" />
                    <Label htmlFor="img-large" className="cursor-pointer">
                      Large
                    </Label>
                  </div>
                </RadioGroup>
              </div>
            </section>

            <Separator />

            {/* ── Field Groups ── */}
            <section className="space-y-2">
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                Fields
              </h3>

              <FieldGroup
                title="Structure Fields"
                fields={STRUCTURE_FIELDS}
                selected={visibleFields.structure}
                onChange={(fields) => setVisibleFields({ structure: fields })}
              />

              <FieldGroup
                title="Properties"
                fields={PROPERTY_FIELDS}
                selected={visibleFields.properties}
                onChange={(fields) => setVisibleFields({ properties: fields })}
              />

              <FieldGroup
                title="Molecule Fields"
                fields={MOLECULE_FIELDS}
                selected={visibleFields.molecule}
                onChange={(fields) => setVisibleFields({ molecule: fields })}
              />

              <FieldGroup
                title="Batch Fields"
                fields={BATCH_FIELDS}
                selected={visibleFields.batch}
                onChange={(fields) => setVisibleFields({ batch: fields })}
              />

              {activeProtocolIds.map((protocolId) => {
                const protocol = protocols.find((p) => p.id === protocolId);
                const protocolName = protocol?.name ?? "Unknown Protocol";
                // One entry per DR intercept + one per numeric readout. The
                // entry's key is the actual grid column-id token, so the
                // check-state reconciles with what's actually rendered.
                const readoutEntries = buildReadoutCustomizerEntries(protocol, protocolId);
                const entryKeys = new Set(readoutEntries.map((e) => e.key));
                // Expand any parent `drc:<rd>` token to the full per-intercept
                // set so a plain `set.has(entryKey)` lookup reflects every
                // intercept the grid is rendering. Without this, a filter-
                // emitted parent token would only "check" the primary entry.
                const expandedColumns = expandParentTokens(protocolColumns, protocols);
                const visibleEntryKeys = expandedColumns.filter((c) => entryKeys.has(c));
                return (
                  <div key={protocolId} className="space-y-0">
                    <FieldGroup
                      title={protocolName}
                      fields={PROTOCOL_FIELDS}
                      selected={visibleFields.protocols[protocolId] ?? []}
                      onChange={(fields) => setProtocolFields(protocolId, fields)}
                    />
                    {readoutEntries.length > 0 && (
                      <FieldGroup
                        title={`${protocolName} — Readouts`}
                        fields={readoutEntries}
                        selected={visibleEntryKeys}
                        onChange={(nextKeysForThisProto) =>
                          onProtocolColumnsChange(
                            replaceProtocolEntries(
                              expandedColumns,
                              entryKeys,
                              nextKeysForThisProto,
                            ),
                          )
                        }
                      />
                    )}
                  </div>
                );
              })}
            </section>
          </div>
        </ScrollArea>

        <div className="shrink-0 border-t border-border px-4 py-3">
          <Button className="w-full" onClick={onUpdate}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Update Report
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

// ─── Collapsible Field Group ────────────────────────────────────────────────

interface FieldGroupProps {
  title: string;
  fields: ReadonlyArray<{ readonly key: string; readonly label: string }>;
  selected: string[];
  onChange: (fields: string[]) => void;
}

function FieldGroup({ title, fields, selected, onChange }: FieldGroupProps) {
  const [isOpen, setIsOpen] = useState(false);
  const allKeys = fields.map((f) => f.key);
  const allChecked = allKeys.every((k) => selected.includes(k));
  const someChecked = selected.length > 0 && !allChecked;

  function handleMasterToggle() {
    onChange(allChecked ? [] : [...allKeys]);
  }

  function handleFieldToggle(key: string) {
    onChange(selected.includes(key) ? selected.filter((k) => k !== key) : [...selected, key]);
  }

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className="flex items-center gap-2 py-1.5">
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="flex items-center text-muted-foreground hover:text-foreground transition-colors"
          >
            {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        </CollapsibleTrigger>

        <Checkbox
          checked={allChecked ? true : someChecked ? "indeterminate" : false}
          onCheckedChange={handleMasterToggle}
          id={`group-${title}`}
        />
        <Label htmlFor={`group-${title}`} className="flex-1 text-sm font-medium cursor-pointer">
          {title}
        </Label>

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <button
            type="button"
            className="hover:text-foreground transition-colors underline-offset-4 hover:underline"
            onClick={() => onChange([...allKeys])}
          >
            All
          </button>
          <span>/</span>
          <button
            type="button"
            className="hover:text-foreground transition-colors underline-offset-4 hover:underline"
            onClick={() => onChange([])}
          >
            None
          </button>
        </div>
      </div>

      <CollapsibleContent>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 pl-10 pb-2">
          {fields.map((field) => (
            <div key={field.key} className="flex items-center gap-2">
              <Checkbox
                checked={selected.includes(field.key)}
                onCheckedChange={() => handleFieldToggle(field.key)}
                id={`field-${title}-${field.key}`}
              />
              <Label htmlFor={`field-${title}-${field.key}`} className="text-sm cursor-pointer">
                {field.label}
              </Label>
            </div>
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
