"use client";

import { MemberName } from "@/shared/components/entity-name";
import { Badge } from "@/shared/components/ui/badge";
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
import { useCanEdit } from "@/shared/hooks/use-current-user";
import { ApiError } from "@/shared/lib/api/custom-instance";
import type { ReviewMeltingStepRequest } from "@/shared/lib/api/model";
import { formatDateTime } from "@/shared/lib/format-date";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import { cn } from "@/shared/lib/utils";
import { useId, useState } from "react";
import { apiReason } from "../hooks/use-instrument-import-wizard";
import {
  useAddMeltingStep,
  useAssignMeltingStep,
  useReviewMeltingStep,
} from "../hooks/use-melting-analysis";
import type { CurvePosition } from "../lib/curve-plot";
import { windowLabel } from "../lib/window-proposal";
import type { MeltingAnalysis, MeltingStep, MeltingStepChange } from "../types";
import { Notice } from "./labelling-table";

const STATUS_LABELS: Record<MeltingStep["status"], string> = {
  unreviewed: "Unreviewed",
  accepted: "Accepted",
  rejected: "Rejected",
};

type Form =
  | { kind: "add"; wellId: string; reason: string }
  | { kind: "correct" | "reject"; step: MeltingStep; reason: string }
  /** Taking a rejected step back: the rejection reason is shown, not silently kept. */
  | { kind: "restore"; step: MeltingStep; status: "accepted" | "unreviewed"; reason: string }
  /** Saying which window the step is the peak of; null leaves it to its temperature. */
  | { kind: "assign"; step: MeltingStep; window: string | null; reason: string };

/** The select's value for "no assignment"; Radix allows no empty value. */
const BY_TEMPERATURE = "__by_temperature__";

const baseline = (s: MeltingStep) => s.instrument_value ?? s.value;

/** A temperature as the value field shows it: two decimals, no trailing zeros. */
export function stepInput(v: number): string {
  return String(Number(v.toFixed(2)));
}

/** The value the field stands for: an untouched rounded copy of the step's
 *  stored or instrument value means that exact value, so it is no change. */
function entered(step: MeltingStep, parsed: number): number {
  for (const v of [step.value, baseline(step)]) if (parsed === Number(stepInput(v))) return v;
  return parsed;
}

const FORM_TITLES = {
  reject: "Reject",
  correct: "Correct",
  assign: "Assign",
  accepted: "Accept",
  unreviewed: "Mark unreviewed",
} as const;

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
  /** The temperature windows on the current signal. */
  windows: readonly { window: string; low: number; high: number }[];
  /** The x unit of the current signal. */
  unit: string;
  /** The value field of the open Add or Correct form; held by the parent so a
   *  plot click can fill it. */
  value: string;
  onValueChange: (value: string) => void;
  onReload: () => Promise<unknown>;
}

/** Review the melting steps of the selected positions on the current signal:
 *  accept, reject, correct, assign to a window, or add one by hand. Nothing
 *  saves until Save, Accept or Clear. */
export function MeltingStepsPanel({
  runId,
  analysis,
  positions,
  channel,
  windows,
  unit,
  value,
  onValueChange,
  onReload,
}: MeltingStepsPanelProps) {
  const canEdit = useCanEdit();
  const editable = canEdit && !analysis.edit_refusal;
  const add = useAddMeltingStep(runId);
  const reviewStep = useReviewMeltingStep(runId);
  const assign = useAssignMeltingStep(runId);
  const [form, setForm] = useState<Form | null>(null);
  const [error, setError] = useState<{ message: string; conflict: boolean } | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false);
  const ids = useId();
  const busy = add.isPending || reviewStep.isPending || assign.isPending || reloading;
  const isWindow = (name: string | null) => windows.some((w) => w.window === name);

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
  /** A null window clears the assignment; a blank reason is left out. */
  const sendAssignment = (step: MeltingStep, window: string | null, why = "") => {
    start();
    assign.mutate(
      {
        stepId: step.id,
        body: { expected_version: step.version, window, ...(why ? { reason: why } : {}) },
      },
      callbacks,
    );
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
    // An assignment needs no reason, and the server takes an unchanged one as no change.
    (form.kind === "assign" ||
      (form.kind === "reject"
        ? reason !== ""
        : form.kind === "restore"
          ? reason !== "" || form.step.value === baseline(form.step)
          : form.kind === "add"
            ? validValue && byWell.has(form.wellId)
            : validValue && (reason !== "" || entered(form.step, parsed) === baseline(form.step))));

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
    } else if (form.kind === "restore") {
      send(form.step, review(form.step, form.status, form.step.value, reason));
    } else if (form.kind === "assign") {
      sendAssignment(form.step, form.window, reason);
    } else {
      send(form.step, review(form.step, "accepted", entered(form.step, parsed), reason));
    }
  };

  /** From rejected, open a form showing the rejection reason; otherwise save at once. */
  const setStatus = (s: MeltingStep, status: "accepted" | "unreviewed") => {
    if (s.status === "rejected") {
      open({ kind: "restore", step: s, status, reason: s.reason ?? "" }, "");
    } else {
      send(s, review(s, status, s.value, s.reason));
    }
  };

  /** Opens on the step's window; a name that is no longer a window counts as none. */
  const openAssign = (s: MeltingStep) => {
    const current = isWindow(s.assigned_window);
    open(
      {
        kind: "assign",
        step: s,
        window: current ? s.assigned_window : null,
        reason: current ? (s.assignment_reason ?? "") : "",
      },
      "",
    );
  };

  const formPosition = form && byWell.get(form.kind === "add" ? form.wellId : form.step.well_id);
  // One peak per position and window: saving takes the window from the peak that has it.
  const replaced =
    form?.kind === "assign" && form.window
      ? analysis.steps.find(
          (o) =>
            o.id !== form.step.id &&
            o.well_id === form.step.well_id &&
            o.channel_key === form.step.channel_key &&
            o.assigned_window === form.window,
        )
      : undefined;

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-3">
        <h3 className="text-sm font-medium">Peaks</h3>
        {editable && positions.length > 0 && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="ml-auto"
            disabled={busy}
            onClick={() => open({ kind: "add", wellId: positions[0].well_id, reason: "" }, "")}
          >
            Add peak
          </Button>
        )}
      </div>

      {analysis.edit_refusal && (
        <p className="text-sm text-muted-foreground">{analysis.edit_refusal}</p>
      )}

      <ul aria-label="Peaks" className="divide-y rounded-md border text-sm">
        {rows.length === 0 ? (
          <li className="p-2 text-muted-foreground">
            {positions.length === 0
              ? "Select a position to review its peaks."
              : "The selected positions have no peaks on this signal."}
          </li>
        ) : (
          rows.map((s) => {
            const rejected = s.status === "rejected";
            const p = byWell.get(s.well_id);
            return (
              <li
                key={s.id}
                className={cn(
                  "space-y-0.5 px-2 py-1.5",
                  rejected && "text-muted-foreground line-through",
                )}
              >
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  {positions.length > 1 && <span className="font-medium">{p?.position_label}</span>}
                  <span className="font-mono tabular-nums">{fmt(s.value)}</span>
                  <span className="text-muted-foreground">{unit}</span>
                  <Badge
                    variant="outline"
                    title={s.instrument_label ?? undefined}
                    className="no-underline"
                  >
                    {`${s.source === "manual" ? "Manual" : "Instrument"} · ${STATUS_LABELS[s.status]}`}
                  </Badge>
                  {s.instrument_value !== null && s.instrument_value !== s.value && (
                    <span className="text-xs text-muted-foreground">{`was ${fmt(s.instrument_value)}`}</span>
                  )}
                  {s.assigned_window &&
                    (isWindow(s.assigned_window) ? (
                      <Badge variant="secondary" className="no-underline">
                        {`→ ${s.assigned_window} (assigned)`}
                      </Badge>
                    ) : (
                      <span className="flex items-center gap-x-1 text-xs text-muted-foreground no-underline">
                        {`Assigned to '${s.assigned_window}', which is not a window on this signal`}
                        {editable && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            disabled={busy}
                            onClick={() => sendAssignment(s, null)}
                          >
                            Clear
                          </Button>
                        )}
                      </span>
                    ))}
                  {editable && (
                    <span className="ml-auto flex flex-wrap gap-x-1 no-underline">
                      {s.status !== "accepted" && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => setStatus(s, "accepted")}
                        >
                          Accept
                        </Button>
                      )}
                      {s.status !== "unreviewed" && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => setStatus(s, "unreviewed")}
                        >
                          Mark unreviewed
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
                            stepInput(s.value),
                          )
                        }
                      >
                        Correct
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={busy}
                        onClick={() => openAssign(s)}
                      >
                        Assign
                      </Button>
                    </span>
                  )}
                </div>
                {(s.reason || s.changed_by) && (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    {s.reason && (
                      <span className="min-w-0 truncate" title={s.reason}>
                        {s.reason}
                      </span>
                    )}
                    {s.changed_by && (
                      <span className="ml-auto shrink-0">
                        <MemberName id={s.changed_by} />
                        {s.changed_at && ` · ${formatDateTime(s.changed_at)}`}
                      </span>
                    )}
                  </div>
                )}
              </li>
            );
          })
        )}
      </ul>

      {form && editable && (
        <div className="space-y-3 rounded-md border p-3">
          <p className="text-sm font-medium">
            {form.kind === "add"
              ? "Add a peak"
              : `${FORM_TITLES[form.kind === "restore" ? form.status : form.kind]} the peak at ${fmt(form.step.value)} ${unit} on ${formPosition?.position_label ?? "this position"}`}
          </p>
          {form.kind === "restore" && (
            <p className="text-xs text-muted-foreground">
              The reason below was given when the peak was rejected. Clear it or change it if it no
              longer applies.
            </p>
          )}
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
            {(form.kind === "add" || form.kind === "correct") && (
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
                        onValueChange(stepInput(form.step.instrument_value as number));
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
            {form.kind === "assign" && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`${ids}-window`}>Window</Label>
                <Select
                  value={form.window ?? BY_TEMPERATURE}
                  onValueChange={(v) =>
                    setForm({
                      ...form,
                      window: v === BY_TEMPERATURE ? null : v,
                      // An untouched stored reason explained the assignment being given up.
                      reason:
                        form.reason === (form.step.assignment_reason ?? "") ? "" : form.reason,
                    })
                  }
                >
                  <SelectTrigger id={`${ids}-window`} size="sm" className="w-48">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {windows.map((w) => (
                      <SelectItem key={w.window} value={w.window}>
                        {windowLabel(w)}
                      </SelectItem>
                    ))}
                    <SelectItem value={BY_TEMPERATURE}>By temperature</SelectItem>
                  </SelectContent>
                </Select>
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
                    : form.kind === "add" ||
                        form.kind === "assign" ||
                        (form.kind === "restore" && form.step.value === baseline(form.step))
                      ? "Optional"
                      : "Required when the value differs from the instrument's"
                }
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
              />
            </div>
          </div>
          {replaced && (
            <p className="text-xs text-muted-foreground">
              {`${replaced.assigned_window} is currently the peak at ${fmt(replaced.value)} ${unit} on this position; saving replaces it.`}
            </p>
          )}
          <div className="flex items-center gap-2">
            {(form.kind === "add" || form.kind === "correct") && (
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
