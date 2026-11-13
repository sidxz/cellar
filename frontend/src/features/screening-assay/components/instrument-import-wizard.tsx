"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useId, useMemo, useRef } from "react";

import { CsvDropzone } from "@/shared/components/csv-dropzone";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { WizardStepIndicator } from "@/shared/components/wizard-step-indicator";
import { formatFileSize } from "@/shared/lib/format-number";
import { useInstrumentFileFormats } from "../hooks/use-instrument-import";
import { useInstrumentImportWizard } from "../hooks/use-instrument-import-wizard";
import {
  type LabellingDraft,
  labellingProblem,
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
} from "../types";
import { StatCard } from "./import-outcome-cards";
import { LabellingTable, Notice } from "./labelling-table";

/** Any file: the API names the formats it reads when it cannot read one. */
const ANY_FILE = {};
/** Radix Select forbids an empty item value; this stands for "no readout". */
const NO_READOUT = "__none__";

interface InstrumentImportWizardProps {
  runId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function InstrumentImportWizard({ runId, open, onOpenChange }: InstrumentImportWizardProps) {
  const w = useInstrumentImportWizard({ runId, onOpenChange });
  const { step, preview, result, isPreviewing, isImporting, canImport, setStep } = w;

  const hints = useMemo(
    () =>
      new Map(
        (preview?.positions ?? []).map((p) => [
          positionKey(p),
          {
            noMatch: !!p.label.trim() && !p.suggestion,
            suggestedId: p.suggestion?.molecule_id ?? null,
          },
        ]),
      ),
    [preview?.positions],
  );

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
                  accept={ANY_FILE}
                  prompt="Drop the instrument's file here, or click to browse"
                />
              </div>
              {w.error && <Notice tone="bad">{w.error}</Notice>}
              {!preview && <SupportedFiles />}
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
            <LabellingTable
              rows={w.draft.positions}
              runId={runId}
              doseUnit={DOSE_UNIT_LABELS[preview.dose_unit as DoseUnit] ?? preview.dose_unit}
              onUpdate={w.updatePosition}
              onSetRole={w.setRole}
              onReplaceRows={w.replacePositions}
              templateName="labelling-template.csv"
              showUse
              hints={hints}
              problem={labellingProblem(w.draft)}
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

// ─── Step 1 — supported files and the recognised file ────────────────────────

/** The formats the API reads, printed as it words them. Nothing while loading or on failure:
 *  the upload works without it. */
function SupportedFiles() {
  const { data } = useInstrumentFileFormats();
  const headingId = useId();
  if (!data?.formats.length) return null;
  return (
    <section aria-labelledby={headingId} className="space-y-2 text-sm">
      <h3 id={headingId} className="font-medium">
        Supported instrument files
      </h3>
      <ul className="space-y-1.5">
        {data.formats.map((f) => (
          <li key={f.id}>
            <div>{f.label}</div>
            <div className="text-muted-foreground">{f.hint}</div>
          </li>
        ))}
      </ul>
    </section>
  );
}

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
        kept with the trace.
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
        <StatCard label="traces to store" value={s.curves} />
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
          They keep their label and traces, but their values will not appear under a compound.
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
        <b>Imported.</b> {result.positions_created} positions, {result.curves_created} traces,{" "}
        {result.values_inserted} readout values.
        {result.file_attached &&
          (result.stored_file_name
            ? ` The original file is on the Files tab as ${result.stored_file_name}.`
            : " The original file is on the Files tab.")}
      </Notice>
      {!result.file_attached && (
        <Notice tone="warn">
          <b>The data is imported.</b>{" "}
          {result.attachment_warning ??
            "The file could not be attached. Upload it on the Files tab."}
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
