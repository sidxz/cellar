"use client";

import { useProtocols, useProtocol } from "@/features/screening-assay/hooks/use-protocols";
import { CURVE_TYPE_LABELS } from "@/features/screening-assay/types";
import { StructureEditorDialog, StructureRenderer } from "@/shared/components/chemistry";
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
import { Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import {
  PROPERTY_OPERATORS,
  STRUCTURE_TYPES,
} from "../../lib/search-query-config";
import type {
  PropertyOperator,
  SelectivityCriterion,
  StructureCriterion,
  StructureSearchType,
} from "../../types";

export function StructureCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: StructureCriterion;
  onChange: (c: StructureCriterion) => void;
  onRemove: () => void;
}) {
  const [editorOpen, setEditorOpen] = useState(false);

  const previewSmiles =
    criterion.search_type === "substructure"
      ? criterion.smarts
      : criterion.search_type === "similarity"
        ? criterion.smiles
        : undefined;

  const isStructureMode =
    criterion.search_type === "substructure" || criterion.search_type === "similarity";

  const editorOutputFormat = criterion.search_type === "substructure" ? "smarts" : "smiles";

  const handleEditorApply = (structure: string) => {
    if (criterion.search_type === "substructure") {
      onChange({ ...criterion, smarts: structure });
    } else {
      onChange({ ...criterion, smiles: structure });
    }
  };

  return (
    <div className="flex items-start gap-2">
      {previewSmiles && previewSmiles.length >= 2 && (
        <div className="shrink-0 rounded border border-border bg-muted/30 p-1">
          <StructureRenderer smiles={previewSmiles} width={100} height={80} />
        </div>
      )}

      <div className="flex flex-1 flex-wrap items-end gap-2">
        <div className="w-48">
          <Label className="text-xs text-muted-foreground">Search Type</Label>
          <Select
            value={criterion.search_type}
            onValueChange={(v) => onChange({ ...criterion, search_type: v as StructureSearchType })}
          >
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
        {criterion.search_type === "substructure" && (
          <div className="flex-1 min-w-[200px]">
            <Label className="text-xs text-muted-foreground">SMARTS</Label>
            <div className="flex gap-1">
              <Input
                className="h-9 font-mono text-xs"
                placeholder="e.g. c1ccccc1"
                value={criterion.smarts ?? ""}
                onChange={(e) => onChange({ ...criterion, smarts: e.target.value })}
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
        {criterion.search_type === "similarity" && (
          <>
            <div className="flex-1 min-w-[200px]">
              <Label className="text-xs text-muted-foreground">SMILES</Label>
              <div className="flex gap-1">
                <Input
                  className="h-9 font-mono text-xs"
                  placeholder="e.g. CCO"
                  value={criterion.smiles ?? ""}
                  onChange={(e) => onChange({ ...criterion, smiles: e.target.value })}
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
            <div className="w-28">
              <Label className="text-xs text-muted-foreground">
                Threshold ({criterion.threshold?.toFixed(2) ?? "0.70"})
              </Label>
              <Input
                className="h-9"
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={criterion.threshold ?? 0.7}
                onChange={(e) => onChange({ ...criterion, threshold: Number(e.target.value) })}
              />
            </div>
          </>
        )}
        {criterion.search_type === "exact" && (
          <div className="flex-1 min-w-[200px]">
            <Label className="text-xs text-muted-foreground">InChI Key</Label>
            <Input
              className="h-9 font-mono text-xs"
              placeholder="e.g. BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
              value={criterion.inchi_key ?? ""}
              onChange={(e) => onChange({ ...criterion, inchi_key: e.target.value })}
            />
          </div>
        )}
        <Button variant="ghost" size="icon" className="h-9 w-9 shrink-0" onClick={onRemove}>
          <Trash2 className="h-4 w-4 text-muted-foreground" />
        </Button>
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

export function SelectivityCriterionRow({
  criterion,
  onChange,
  onRemove,
}: {
  criterion: SelectivityCriterion;
  onChange: (c: SelectivityCriterion) => void;
  onRemove: () => void;
}) {
  const { data: protocols } = useProtocols();
  const activeProtocols = protocols?.filter((p) => p.status === "active");

  // Transient picker state: the criterion stores readout-def UUIDs only
  // (post-033). We still ask the user to pick a protocol first so the
  // readout-def dropdown stays scoped.
  const [targetProtocolId, setTargetProtocolId] = useState<string>("");
  const [counterProtocolId, setCounterProtocolId] = useState<string>("");
  const { data: targetProtocol } = useProtocol(targetProtocolId);
  const { data: counterProtocol } = useProtocol(counterProtocolId);

  const targetDrReadouts =
    targetProtocol?.readout_definitions?.filter((rd) => rd.dose_response_config) ?? [];
  const counterDrReadouts =
    counterProtocol?.readout_definitions?.filter((rd) => rd.dose_response_config) ?? [];

  return (
    <div className="space-y-2 rounded border border-dashed border-border p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">
          Selectivity — counter / target ratio
        </span>
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={onRemove}>
          <Trash2 className="h-4 w-4 text-muted-foreground" />
        </Button>
      </div>
      <div className="flex items-end gap-2 flex-wrap">
        <div className="w-44">
          <Label className="text-xs text-muted-foreground">Target Protocol</Label>
          <Select
            value={targetProtocolId || undefined}
            onValueChange={(v) => {
              setTargetProtocolId(v);
              onChange({ ...criterion, target_readout_definition_id: "" });
            }}
          >
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              {activeProtocols?.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="w-44">
          <Label className="text-xs text-muted-foreground">Readout</Label>
          <Select
            value={criterion.target_readout_definition_id || undefined}
            onValueChange={(v) => onChange({ ...criterion, target_readout_definition_id: v })}
            disabled={!targetProtocolId}
          >
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              {targetDrReadouts.map((rd) => {
                const ct = rd.dose_response_config?.curve_type;
                const suffix = ct ? ` (${CURVE_TYPE_LABELS[ct] ?? ct.toUpperCase()})` : "";
                return (
                  <SelectItem key={rd.id} value={rd.id}>
                    {rd.name}{suffix}
                  </SelectItem>
                );
              })}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="flex items-end gap-2 flex-wrap">
        <div className="w-44">
          <Label className="text-xs text-muted-foreground">Counter Protocol</Label>
          <Select
            value={counterProtocolId || undefined}
            onValueChange={(v) => {
              setCounterProtocolId(v);
              onChange({ ...criterion, counter_readout_definition_id: "" });
            }}
          >
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              {activeProtocols?.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="w-44">
          <Label className="text-xs text-muted-foreground">Readout</Label>
          <Select
            value={criterion.counter_readout_definition_id || undefined}
            onValueChange={(v) => onChange({ ...criterion, counter_readout_definition_id: v })}
            disabled={!counterProtocolId}
          >
            <SelectTrigger className="h-9">
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              {counterDrReadouts.map((rd) => {
                const ct = rd.dose_response_config?.curve_type;
                const suffix = ct ? ` (${CURVE_TYPE_LABELS[ct] ?? ct.toUpperCase()})` : "";
                return (
                  <SelectItem key={rd.id} value={rd.id}>
                    {rd.name}{suffix}
                  </SelectItem>
                );
              })}
            </SelectContent>
          </Select>
        </div>
        <div className="w-20">
          <Label className="text-xs text-muted-foreground">Ratio</Label>
          <Select
            value={criterion.ratio_operator}
            onValueChange={(v) => onChange({ ...criterion, ratio_operator: v as PropertyOperator })}
          >
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PROPERTY_OPERATORS.filter((o) => o.value !== "between").map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="w-24">
          <Label className="text-xs text-muted-foreground">Value</Label>
          <Input
            className="h-9"
            type="number"
            placeholder="e.g. 100"
            value={criterion.ratio_value ?? ""}
            onChange={(e) =>
              onChange({ ...criterion, ratio_value: e.target.value ? Number(e.target.value) : 0 })
            }
          />
        </div>
      </div>
    </div>
  );
}
