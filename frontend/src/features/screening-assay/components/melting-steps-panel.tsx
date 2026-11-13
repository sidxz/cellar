"use client";

import { MemberName } from "@/shared/components/entity-name";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { useCanEdit } from "@/shared/hooks/use-current-user";
import { ApiError } from "@/shared/lib/api/custom-instance";
import type { ReviewMeltingStepRequest } from "@/shared/lib/api/model";
import { formatDateTime } from "@/shared/lib/format-date";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import { cn } from "@/shared/lib/utils";
import { useId, useState } from "react";
import { apiReason } from "../hooks/use-instrument-import-wizard";
import { useAddMeltingStep, useReviewMeltingStep } from "../hooks/use-melting-analysis";
import type { CurvePosition } from "../lib/curve-plot";
import type { MeltingAnalysis, MeltingStep, MeltingStepChange } from "../types";
import { Notice } from "./labelling-table";

const STATUS_LABELS: Record<MeltingStep["status"], string> = {
  unreviewed: "Unreviewed",
  accepted: "Accepted",
  rejected: "Rejected",
};

type Form =
  | { kind: "add"; wellId: string; reason: string }
  | { kind: "correct" | "reject"; step: MeltingStep; reason: string };

function fmt(v: number): string {
  return formatMeasurementValue(v, 4);
}

/** The PATCH body; a blank reason is left out. */
function review(
  step: MeltingStep,
  status: MeltingStep["status"],
  value: number,
  reason: string | null,
): ReviewMeltingStepRequest {
  const r = reason?.trim();
  return { expected_version: step.version, status, value, ...(r ? { reason: r } : {}) };
}

export interface MeltingStepsPanelProps {
  runId: string;
  analysis: MeltingAnalysis;
  /** The selected positions, in holder order. */
  positions: readonly CurvePosition[];
  /** The current signal's key. */
  channel: string | null;
  /** The x unit of the current signal. */
  unit: string;
  /** The value field of the open Add or Correct form; held by the parent so a
   *  plot click can fill it. */
  value: string;
  onValueChange: (value: string) => void;
  onReload: () => Promise<unknown>;
}

/** Review the melting steps of the selected positions on the current signal:
 *  accept, reject, correct, or add one by hand. Nothing saves until Save or Accept. */
export function MeltingStepsPanel({
  runId,
  analysis,
  positions,
  channel,
  unit,
  value,
  onValueChange,
  onReload,
}: MeltingStepsPanelProps) {
  const canEdit = useCanEdit();
  const editable = canEdit && !analysis.edit_refusal;
  const add = useAddMeltingStep(runId);
  const reviewStep = useReviewMeltingStep(runId);
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState<{ message: string; conflict: boolean } | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false);
  const ids = useId();
  const busy = add.isPending || reviewStep.isPending || reloading;

  const order = new Map(positions.map((p, i) => [p.well_id, i]));
  const byWell = new Map(positions.map((p) => [p.well_id, p]));
  const rows = analysis.steps
    .filter((s) => s.channel_key === channel && order.has(s.well_id))
    .sort((a, b) => (order.get(a.well_id) ?? 0) - (order.get(b.well_id) ?? 0) || a.value - b.value);

  const callbacks = {
    onSuccess: (change: MeltingStepChange) => {
      setForm(null);
      setWarning(change.compute_warning);
    },
    onError: (e: unknown) =>
      setError({
        message: apiReason(e),
        conflict: e instanceof ApiError && e.status === 409,
      }),
  };
  const start = () => {
    setError(null);
    setWarning(null);
  };
  const send = (step: MeltingStep, body: ReviewMeltingStepRequest) => {
    start();
    reviewStep.mutate({ stepId: step.id, body }, callbacks);
  };

  const open = (next: Form, initialValue: string) => {
    start();
    setForm(next);
    onValueChange(initialValue);
  };

  const reload = async () => {
    setReloading(true);
    try {
      await onReload();
    } finally {
      setReloading(false);
    }
    setError(null);
    setForm(null);
  };

  const parsed = value.trim() === "" ? Number.NaN : Number(value);
  const validValue = Number.isFinite(parsed);
  const reason = form?.reason.trim() ?? "";
  const canSave =
    !busy &&
    !!form &&
    (form.kind === "reject"
      ? reason !== ""
      : form.kind === "add"
        ? validValue && byWell.has(form.wellId)
        : validValue &&
          (reason !== "" || parsed === (form.step.instrument_value ?? form.step.value)));

  const save = () => {
    if (!form || !canSave) return;
    if (form.kind === "add") {
      start();
      add.mutate(
        {
          well_id: form.wellId,
          channel_key: channel ?? "",
          value: parsed,
          ...(reason ? { reason } : {}),
        },
        callbacks,
      );
    } else if (form.kind === "reject") {
      send(form.step, review(form.step, "rejected", form.step.value, reason));
    } else {
      send(form.step, review(form.step, "accepted", parsed, reason));
    }
  };

  const formPosition = form && byWell.get(form.kind === "add" ? form.wellId : form.step.well_id);

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-3">
        <h3 className="text-sm font-medium">Melting steps</h3>
        {editable && positions.length > 0 && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="ml-auto"
            disabled={busy}
            onClick={() => open({ kind: "add", wellId: positions[0].well_id, reason: "" }, "")}
          >
            Add step
          </Button>
        )}
      </div>

      {analysis.edit_refusal && (
        <p className="text-sm text-muted-foreground">{analysis.edit_refusal}</p>
      )}

      <div className="rounded-md border">
        <Table aria-label="Melting steps">
          <TableHeader>
            <TableRow>
              <TableHead>Position</TableHead>
              <TableHead>Label</TableHead>
              <TableHead>Batch</TableHead>
              <TableHead className="text-right">Value ({unit})</TableHead>
              <TableHead className="text-right">Instrument value</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Changed</TableHead>
              {editable && <TableHead />}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={editable ? 10 : 9} className="text-muted-foreground">
                  {positions.length === 0
                    ? "Select positions above to review their melting steps."
                    : "The selected positions have no melting steps on this signal."}
                </TableCell>
              </TableRow>
            ) : (
              rows.map((s) => {
                const p = byWell.get(s.well_id);
                const rejected = s.status === "rejected";
                return (
                  <TableRow
                    key={s.id}
                    className={cn(rejected && "text-muted-foreground line-through")}
                  >
                    <TableCell>{p?.position_label}</TableCell>
                    <TableCell>{p?.label}</TableCell>
                    <TableCell>{p?.batch_number ?? "None"}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {fmt(s.value)}
                    </TableCell>
                    <TableCell className="text-right font-mono tabular-nums">
                      {s.instrument_value !== null && s.instrument_value !== s.value
                        ? fmt(s.instrument_value)
                        : ""}
                    </TableCell>
                    <TableCell title={s.instrument_label ?? undefined}>
                      {s.source === "manual" ? "Manual" : "Instrument"}
                    </TableCell>
                    <TableCell>{STATUS_LABELS[s.status]}</TableCell>
                    <TableCell className="whitespace-normal">{s.reason}</TableCell>
                    <TableCell className="text-xs">
                      {s.changed_by && (
                        <>
                          <MemberName id={s.changed_by} />
                          {s.changed_at && ` · ${formatDateTime(s.changed_at)}`}
                        </>
                      )}
                    </TableCell>
                    {editable && (
                      <TableCell className="space-x-1 text-right no-underline">
                        {s.status !== "accepted" && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            disabled={busy}
                            onClick={() => send(s, review(s, "accepted", s.value, s.reason))}
                          >
                            Accept
                          </Button>
                        )}
                        {!rejected && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            disabled={busy}
                            onClick={() =>
                              open({ kind: "reject", step: s, reason: s.reason ?? "" }, "")
                            }
                          >
                            Reject
                          </Button>
                        )}
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() =>
                            open(
                              { kind: "correct", step: s, reason: s.reason ?? "" },
                              String(s.value),
                            )
                          }
                        >
                          Correct
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      {form && editable && (
        <div className="space-y-3 rounded-md border p-3">
          <p className="text-sm font-medium">
            {form.kind === "add"
              ? "Add a melting step"
              : `${form.kind === "reject" ? "Reject" : "Correct"} the step at ${fmt(form.step.value)} ${unit} on ${formPosition?.position_label ?? "this position"}`}
          </p>
          <div className="flex flex-wrap items-end gap-3">
            {form.kind === "add" && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`${ids}-position`}>Position</Label>
                <Select
                  value={form.wellId}
                  onValueChange={(wellId) => setForm({ ...form, wellId })}
                >
                  <SelectTrigger id={`${ids}-position`} size="sm" className="w-48">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {positions.map((p) => (
                      <SelectItem key={p.well_id} value={p.well_id}>
                        {p.label ? `${p.position_label} · ${p.label}` : p.position_label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {form.kind !== "reject" && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`${ids}-value`}>Value</Label>
                <div className="flex items-center gap-2">
                  <Input
                    id={`${ids}-value`}
                    type="number"
                    step="any"
                    className="h-8 w-28"
                    value={value}
                    onChange={(e) => onValueChange(e.target.value)}
                  />
                  <span className="text-sm text-muted-foreground">{unit}</span>
                  {form.kind === "correct" && form.step.instrument_value !== null && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        onValueChange(String(form.step.instrument_value));
                        // The reason explained a value that is being given up.
                        setForm({ ...form, reason: "" });
                      }}
                    >
                      Use instrument value
                    </Button>
                  )}
                </div>
              </div>
            )}
            <div className="flex min-w-64 flex-1 flex-col gap-1.5">
              <Label htmlFor={`${ids}-reason`}>Reason</Label>
              <Input
                id={`${ids}-reason`}
                className="h-8"
                maxLength={500}
                placeholder={
                  form.kind === "reject"
                    ? "Required"
                    : form.kind === "add"
                      ? "Optional"
                      : "Required when the value differs from the instrument's"
                }
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            {form.kind !== "reject" && (
              <span className="text-xs text-muted-foreground">
                Click a trace on the plot to fill the value.
              </span>
            )}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="ml-auto"
              disabled={busy}
              onClick={() => setForm(null)}
            >
              Cancel
            </Button>
            <Button type="button" size="sm" disabled={!canSave} onClick={save}>
              {busy ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      )}

      {error && (
        <Notice tone="bad">
          <div className="flex flex-wrap items-center gap-3">
            <span>{error.message}</span>
            {error.conflict && (
              <Button
                size="sm"
                variant="outline"
                className="ml-auto"
                disabled={reloading}
                onClick={reload}
              >
                Reload
              </Button>
            )}
          </div>
        </Notice>
      )}
      {warning && <Notice tone="warn">{warning}</Notice>}
    </section>
  );
}
