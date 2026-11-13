"use client";

import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { type ReactNode, useCallback, useMemo, useRef, useState } from "react";

import { BatchSelector } from "@/features/inventory/components/batch-selector";
import { MoleculeSelector } from "@/features/inventory/components/molecule-selector";
import { CsvDropzone } from "@/shared/components/csv-dropzone";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { WizardStepIndicator } from "@/shared/components/wizard-step-indicator";
import { formatFileSize } from "@/shared/lib/format-number";
import { cn } from "@/shared/lib/utils";
import { useInstrumentImportWizard } from "../hooks/use-instrument-import-wizard";
import {
  type LabellingDraft,
  type PositionDraft,
  labellingSummary,
  positionKey,
  selectableReadouts,
  seriesKey,
} from "../lib/instrument-labelling";
import {
  DOSE_UNIT_LABELS,
  type DoseUnit,
  type InstrumentImportResult,
  type InstrumentPreview,
  WELL_TYPE_LABELS,
  type WellType,
} from "../types";
import { StatCard } from "./import-outcome-cards";

const XLSX_ACCEPT = {
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
};
const WELL_TYPES = Object.keys(WELL_TYPE_LABELS) as WellType[];
/** Radix Select forbids an empty item value; this stands for "no readout". */
const NO_READOUT = "__none__";

/** Left-pinned columns of the labelling table: select (fixed width) then Position. */
const STICKY_SELECT = "sticky left-0 z-[1] w-10 min-w-10";
const STICKY_POSITION = "sticky left-10 z-[1] whitespace-nowrap";
/** ``bg-muted/40`` over the background, made opaque for pinned cells. */
const SELECTED_OPAQUE = "bg-[color-mix(in_oklab,var(--muted)_40%,var(--background))]";

const isBadDose = (dose: string) =>
  dose.trim() !== "" && !(Number.isFinite(Number(dose)) && Number(dose) >= 0);

function Notice({ tone, children }: { tone: "ok" | "warn" | "bad"; children: ReactNode }) {
  return (
    <div
      role={tone === "bad" ? "alert" : undefined}
      className={cn(
        "rounded-md border p-3 text-sm",
        tone === "ok" && "border-green-500/30 bg-green-500/5",
        tone === "warn" &&
          "border-amber-500/30 bg-amber-500/5 text-amber-700 dark:text-amber-300/90",
        tone === "bad" && "border-destructive/40 bg-destructive/5 text-destructive",
      )}
    >
      {children}
    </div>
  );
}

interface InstrumentImportWizardProps {
  runId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function InstrumentImportWizard({ runId, open, onOpenChange }: InstrumentImportWizardProps) {
  const w = useInstrumentImportWizard({ runId, open, onOpenChange });
  const { step, preview, result, isPreviewing, isImporting, canImport, setStep } = w;

  const openPickerRef = useRef<(() => void) | null>(null);
  const handleOpenReady = useCallback((open: () => void) => {
    openPickerRef.current = open;
  }, []);

  return (
    <Dialog open={open} onOpenChange={w.handleOpenChange}>
      {/* Header, steps and footer stay put; only the body below them scrolls,
          and in step 2 only the labelling table does. */}
      <DialogContent className="flex max-h-[90vh] w-[min(95vw,1280px)] max-w-[1280px] flex-col overflow-hidden sm:max-w-[1280px]">
        <DialogHeader>
          <DialogTitle>Import instrument file</DialogTitle>
          <DialogDescription>
            Upload the instrument&apos;s file, say what was in each position and choose where its
            own calculated values are stored.
          </DialogDescription>
        </DialogHeader>

        <WizardStepIndicator
          steps={["Upload", "Label positions", "Map reported values", "Review and import"]}
          current={step}
        />

        <div className="flex min-h-0 min-w-0 flex-col overflow-y-auto">
          {step === 1 && (
            <div className="space-y-4 py-2">
              {/* Stays mounted once a file is recognised so "Choose another file" can open it. */}
              <div hidden={!!preview}>
                <CsvDropzone
                  file={w.file}
                  isPending={isPreviewing}
                  onFile={w.handleFile}
                  onOpenReady={handleOpenReady}
                  accept={XLSX_ACCEPT}
                  prompt="Drop the instrument's file here, or click to browse"
                  hint=".xlsx"
                />
              </div>
              {w.error && <Notice tone="bad">{w.error}</Notice>}
              {preview && w.file && (
                <RecognisedFile
                  preview={preview}
                  file={w.file}
                  onChooseAnother={() => openPickerRef.current?.()}
                />
              )}
            </div>
          )}

          {step === 2 && preview && (
            <LabelStep
              preview={preview}
              draft={w.draft}
              onUpdate={w.updatePosition}
              onSetRole={w.setRole}
            />
          )}

          {step === 3 && preview && (
            <MapStep preview={preview} draft={w.draft} onSetReadout={w.setSeriesReadout} />
          )}

          {step === 4 && preview && !result && (
            <ReviewStep preview={preview} draft={w.draft} error={w.error} />
          )}
          {step === 4 && result && <ResultView result={result} />}
        </div>

        <DialogFooter className="gap-2">
          {step > 1 && !result && (
            <Button
              variant="ghost"
              onClick={() => setStep((step - 1) as 1 | 2 | 3)}
              disabled={isImporting}
            >
              <ChevronLeft className="h-4 w-4" /> Back
            </Button>
          )}
          {step === 1 && !preview && (
            <Button onClick={() => openPickerRef.current?.()} disabled={isPreviewing}>
              Choose file
            </Button>
          )}
          {step === 1 && preview && (
            <Button onClick={() => setStep(2)}>
              Continue <ChevronRight className="h-4 w-4" />
            </Button>
          )}
          {step === 2 && (
            <Button onClick={() => setStep(3)} disabled={!canImport}>
              Continue <ChevronRight className="h-4 w-4" />
            </Button>
          )}
          {step === 3 && (
            <Button onClick={() => setStep(4)}>
              Continue <ChevronRight className="h-4 w-4" />
            </Button>
          )}
          {step === 4 && !result && (
            <Button onClick={w.handleImport} disabled={!canImport || isImporting}>
              {isImporting ? "Importing…" : "Import"}
            </Button>
          )}
          {step === 4 && result && <Button onClick={() => w.handleOpenChange(false)}>Done</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Step 1 — recognised file ─────────────────────────────────────────────────

function RecognisedFile({
  preview,
  file,
  onChooseAnother,
}: {
  preview: InstrumentPreview;
  file: File;
  onChooseAnother: () => void;
}) {
  const rows: [string, string][] = [
    ["Format", preview.reader_label],
    ["Holder", preview.holder.label],
    ["Signals", preview.channels.map((c) => c.label).join(" · ")],
    ...Object.entries(preview.settings),
  ];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 rounded-md border p-3 text-sm">
        <Badge variant="outline" className="border-green-500/30 bg-green-500/10 text-green-400">
          Recognised
        </Badge>
        <span className="font-mono">{file.name}</span>
        <span className="text-xs text-muted-foreground">{formatFileSize(file.size)}</span>
        <Button variant="ghost" size="sm" className="ml-auto" onClick={onChooseAnother}>
          Choose another file
        </Button>
      </div>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground">{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// ─── Step 2 — label positions ─────────────────────────────────────────────────

function LabelStep({
  preview,
  draft,
  onUpdate,
  onSetRole,
}: {
  preview: InstrumentPreview;
  draft: LabellingDraft;
  onUpdate: (key: string, patch: Partial<PositionDraft>) => void;
  onSetRole: (keys: ReadonlySet<string>, wellType: WellType) => void;
}) {
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [bulkRole, setBulkRole] = useState<WellType>("sample");
  const fromFile = useMemo(
    () => new Map(preview.positions.map((p) => [positionKey(p), p])),
    [preview.positions],
  );
  const allKeys = draft.positions.map(positionKey);
  const allSelected = allKeys.length > 0 && selected.size === allKeys.length;

  const toggle = (key: string, on: boolean) =>
    setSelected((s) => {
      const next = new Set(s);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });

  const unit = DOSE_UNIT_LABELS[preview.dose_unit as DoseUnit] ?? preview.dose_unit;

  return (
    <div className="flex min-h-0 flex-col gap-3 py-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">
          {selected.size} row{selected.size === 1 ? "" : "s"} selected
        </span>
        <span className="ml-2 text-muted-foreground">Set role</span>
        <Select value={bulkRole} onValueChange={(v) => setBulkRole(v as WellType)}>
          <SelectTrigger className="h-8 w-44" aria-label="Role for selected rows">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {WELL_TYPES.map((t) => (
              <SelectItem key={t} value={t}>
                {WELL_TYPE_LABELS[t]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          size="sm"
          variant="outline"
          disabled={selected.size === 0}
          onClick={() => onSetRole(selected, bulkRole)}
        >
          Apply to selected
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={selected.size === 0}
          onClick={() => {
            for (const key of selected) onUpdate(key, { used: false });
            setSelected(new Set());
          }}
        >
          Mark unused
        </Button>
        <span className="ml-auto text-xs text-muted-foreground">
          Concentration is in {unit}, the protocol&apos;s dose unit
        </span>
      </div>

      {/* The only scroller in this step: header row sticks to the top, the
          select and Position columns stick to the left. */}
      <div className="min-h-0 overflow-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-muted">
            <tr className="border-b">
              <th className={cn(STICKY_SELECT, "bg-muted px-3 py-2")}>
                <Checkbox
                  aria-label="Select all positions"
                  checked={allSelected}
                  onCheckedChange={(on) => setSelected(new Set(on === true ? allKeys : []))}
                />
              </th>
              <th className={cn(STICKY_POSITION, "bg-muted px-3 py-2 text-left font-medium")}>
                Position
              </th>
              <th className="px-3 py-2 text-left font-medium">Label</th>
              <th className="px-3 py-2 text-left font-medium">Role</th>
              <th className="px-3 py-2 text-left font-medium">Compound</th>
              <th className="px-3 py-2 text-left font-medium">Batch</th>
              <th className="px-3 py-2 text-left font-medium">Conc. ({unit})</th>
              <th className="px-3 py-2 text-left font-medium">Note</th>
              <th className="px-3 py-2 text-left font-medium">Use</th>
            </tr>
          </thead>
          <tbody>
            {draft.positions.map((p) => {
              const key = positionKey(p);
              const original = fromFile.get(key);
              return (
                <PositionRow
                  key={key}
                  position={p}
                  selected={selected.has(key)}
                  noMatch={!!original?.label.trim() && !original.suggestion}
                  suggestedId={original?.suggestion?.molecule_id ?? null}
                  onToggle={(on) => toggle(key, on)}
                  onUpdate={(patch) => onUpdate(key, patch)}
                />
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PositionRow({
  position: p,
  selected,
  noMatch,
  suggestedId,
  onToggle,
  onUpdate,
}: {
  position: PositionDraft;
  selected: boolean;
  noMatch: boolean;
  suggestedId: string | null;
  onToggle: (on: boolean) => void;
  onUpdate: (patch: Partial<PositionDraft>) => void;
}) {
  const cell = "px-3 py-1.5 align-middle";
  // Opaque, so scrolled cells pass beneath; matches the row's selected tint.
  const stickyBg = selected ? SELECTED_OPAQUE : "bg-background";
  const checkbox = (
    <td className={cn(cell, STICKY_SELECT, stickyBg)}>
      <Checkbox
        aria-label={`Select ${p.positionLabel}`}
        checked={selected}
        onCheckedChange={(on) => onToggle(on === true)}
      />
    </td>
  );

  if (!p.used) {
    return (
      <tr className="border-b text-muted-foreground last:border-b-0">
        {checkbox}
        <td className={cn(cell, STICKY_POSITION, stickyBg)}>{p.positionLabel}</td>
        <td className={cell}>{p.label || "empty"}</td>
        <td className={cell}>{WELL_TYPE_LABELS[p.wellType]}</td>
        <td className={cell}>{p.moleculeName ?? "No compound"}</td>
        <td className={cell}>None</td>
        <td className={cell}>{p.dose}</td>
        <td className={cell}>{p.note}</td>
        <td className={cell}>
          <Button size="sm" variant="ghost" onClick={() => onUpdate({ used: true })}>
            Use again
          </Button>
        </td>
      </tr>
    );
  }

  return (
    <tr className={cn("border-b last:border-b-0", selected && "bg-muted/40")}>
      {checkbox}
      <td className={cn(cell, STICKY_POSITION, stickyBg)}>{p.positionLabel}</td>
      <td className={cell}>
        <Input
          className="h-8 w-44"
          aria-label={`Label for ${p.positionLabel}`}
          placeholder="No name in file"
          value={p.label}
          aria-invalid={p.label.length > 200}
          onChange={(e) => onUpdate({ label: e.target.value })}
        />
      </td>
      <td className={cell}>
        <Select value={p.wellType} onValueChange={(v) => onUpdate({ wellType: v as WellType })}>
          <SelectTrigger className="h-8 w-40" aria-label={`Role for ${p.positionLabel}`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {WELL_TYPES.map((t) => (
              <SelectItem key={t} value={t}>
                {WELL_TYPE_LABELS[t]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </td>
      <td className={cell}>
        {p.moleculeId ? (
          <div className="flex items-center gap-1.5 whitespace-nowrap">
            <span>{p.moleculeName}</span>
            {p.moleculeId === suggestedId && (
              <Badge
                variant="outline"
                className="border-green-500/30 bg-green-500/10 text-green-400"
              >
                matched
              </Badge>
            )}
            <Button
              size="icon"
              variant="ghost"
              className="h-6 w-6"
              aria-label={`Change compound for ${p.positionLabel}`}
              onClick={() =>
                onUpdate({ moleculeId: null, moleculeName: null, batchId: null, batchOptions: [] })
              }
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-1.5">
            {noMatch && <Badge variant="outline">No match</Badge>}
            <MoleculeSelector
              selectedId={null}
              onSelect={(id, mol) =>
                onUpdate({
                  moleculeId: id,
                  moleculeName: mol?.name ?? null,
                  batchId: null,
                  batchOptions: [],
                })
              }
            />
          </div>
        )}
      </td>
      <td className={cell}>
        {p.moleculeId ? (
          <div className="flex items-center gap-1.5">
            <BatchSelector
              moleculeId={p.moleculeId}
              selectedId={p.batchId}
              onSelect={(batchId) => onUpdate({ batchId })}
            />
            {!p.batchId && (
              <Badge
                variant="outline"
                className="border-amber-500/30 bg-amber-500/10 text-amber-400"
              >
                not chosen
              </Badge>
            )}
          </div>
        ) : (
          <span className="text-muted-foreground">None</span>
        )}
      </td>
      <td className={cell}>
        <Input
          className="h-8 w-28 text-right"
          inputMode="decimal"
          aria-label={`Concentration for ${p.positionLabel}`}
          value={p.dose}
          aria-invalid={isBadDose(p.dose)}
          onChange={(e) => onUpdate({ dose: e.target.value })}
        />
      </td>
      <td className={cell}>
        <Input
          className="h-8 w-48"
          aria-label={`Note for ${p.positionLabel}`}
          placeholder="Note"
          value={p.note}
          aria-invalid={p.note.length > 1000}
          onChange={(e) => onUpdate({ note: e.target.value })}
        />
      </td>
      <td className={cell}>
        <Badge variant="outline" className="border-green-500/30 bg-green-500/10 text-green-400">
          Used
        </Badge>
      </td>
    </tr>
  );
}

// ─── Step 3 — map reported values ─────────────────────────────────────────────

function MapStep({
  preview,
  draft,
  onSetReadout,
}: {
  preview: InstrumentPreview;
  draft: LabellingDraft;
  onSetReadout: (key: string, readoutId: string | null) => void;
}) {
  const channelLabel = new Map(preview.channels.map((c) => [c.key, c.label]));
  return (
    <div className="space-y-3 py-2">
      <p className="text-sm text-muted-foreground">
        The instrument&apos;s own software calculated these values. Choose which of the
        protocol&apos;s readouts each one is stored in, or leave it out. Values left out are still
        kept with the curve.
      </p>
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr className="border-b">
              <th className="px-3 py-2 text-left font-medium">Reported value</th>
              <th className="px-3 py-2 text-left font-medium">Signal</th>
              <th className="px-3 py-2 text-right font-medium">Positions</th>
              <th className="px-3 py-2 text-left font-medium">Unit</th>
              <th className="px-3 py-2 text-left font-medium">Store in readout</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {preview.series.map((s) => {
              const key = seriesKey(s);
              const chosen = draft.readoutBySeries[key] ?? null;
              return (
                <tr key={key} className="border-b last:border-b-0">
                  <td className="px-3 py-2">{s.label}</td>
                  <td className="px-3 py-2">{channelLabel.get(s.channel) ?? s.channel}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{s.count}</td>
                  <td className="px-3 py-2">{s.unit}</td>
                  <td className="px-3 py-2">
                    <Select
                      value={chosen ?? NO_READOUT}
                      onValueChange={(v) => onSetReadout(key, v === NO_READOUT ? null : v)}
                    >
                      <SelectTrigger className="h-8 w-72" aria-label={`Readout for ${s.label}`}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NO_READOUT}>Don&apos;t store</SelectItem>
                        {selectableReadouts(preview, s, draft.readoutBySeries).map((r) => (
                          <SelectItem key={r.id} value={r.id} disabled={r.disabled}>
                            {r.name}
                            {r.reason ? ` · ${r.reason}` : ""}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </td>
                  <td className="px-3 py-2">
                    {chosen === null ? (
                      <span className="text-muted-foreground">Left out</span>
                    ) : chosen === s.suggested_readout_definition_id ? (
                      <Badge
                        variant="outline"
                        className="border-green-500/30 bg-green-500/10 text-green-400"
                      >
                        Same name
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">Chosen by hand</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {preview.warnings.map((warning) => (
        <Notice key={warning} tone="warn">
          {warning}
        </Notice>
      ))}
    </div>
  );
}

// ─── Step 4 — review and import ───────────────────────────────────────────────

function ReviewStep({
  preview,
  draft,
  error,
}: {
  preview: InstrumentPreview;
  draft: LabellingDraft;
  error: string | null;
}) {
  const s = labellingSummary(draft, preview);
  return (
    <div className="space-y-3 py-2">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <StatCard label="positions used" value={s.used} />
        <StatCard label="positions unused" value={s.unused} />
        <StatCard
          label="used positions without a batch"
          value={s.withoutBatch}
          accent={s.withoutBatch > 0 ? "warn" : undefined}
        />
        <StatCard label="curves to store" value={s.curves} />
        <StatCard
          label={s.unused > 0 ? "readout values to write, at most" : "readout values to write"}
          value={s.values}
        />
      </div>
      {s.withoutBatch > 0 && (
        <Notice tone="warn">
          <b>
            {s.withoutBatch} position{s.withoutBatch === 1 ? " has" : "s have"} no batch.
          </b>{" "}
          They keep their label and curves, but their values will not appear under a compound.
        </Notice>
      )}
      {preview.warnings.map((warning) => (
        <Notice key={warning} tone="warn">
          {warning}
        </Notice>
      ))}
      {error && <Notice tone="bad">{error}</Notice>}
    </div>
  );
}

function ResultView({ result }: { result: InstrumentImportResult }) {
  const warnings = [...result.warnings, result.compute_warning].filter((w): w is string => !!w);
  return (
    <div className="space-y-3 py-2">
      <Notice tone="ok">
        <b>Imported.</b> {result.positions_created} positions, {result.curves_created} curves,{" "}
        {result.values_inserted} readout values.
        {result.file_attached && " The original file is on the Files tab."}
      </Notice>
      {!result.file_attached && (
        <Notice tone="warn">
          <b>The file could not be attached.</b> The data is imported; upload the workbook on the
          Files tab.
          {result.attachment_warning && ` (${result.attachment_warning})`}
        </Notice>
      )}
      {warnings.map((warning) => (
        <Notice key={warning} tone="warn">
          {warning}
        </Notice>
      ))}
    </div>
  );
}
