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
import { type ReactNode, useEffect, useId, useState } from "react";
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

type Range = { window: string; low: number; high: number };

/** An unreviewed peak has no status word: its chip reads only where it came from. */
const STATUS_LABELS: Record<MeltingStep["status"], string | null> = {
  unreviewed: null,
  accepted: "Reviewed",
  rejected: "Excluded",
};

type Form =
  /** A window named here is assigned in the same save. */
  | { kind: "add"; wellId: string; window: string | null; reason: string }
  | { kind: "correct" | "reject"; step: MeltingStep; reason: string }
  /** Taking a rejected step back: the rejection reason is shown, not silently kept. */
  | { kind: "restore"; step: MeltingStep; status: "accepted" | "unreviewed"; reason: string }
  /** Saying which window the step is the peak of; null leaves it to its temperature. */
  | { kind: "assign"; step: MeltingStep; window: string | null; reason: string };

/** The select's value for "no assignment"; Radix allows no empty value. */
const BY_TEMPERATURE = "__by_temperature__";

const baseline = (s: MeltingStep) => s.instrument_value ?? s.value;

/** `From instrument · Reviewed`; `Placed by hand` while unreviewed. */
export function peakKind(s: MeltingStep): string {
  const source = s.source === "manual" ? "Placed by hand" : "From instrument";
  return [source, STATUS_LABELS[s.status]].filter(Boolean).join(" · ");
}

const inRange = (value: number, w: Range) => value >= w.low && value <= w.high;

/** Whether saying which transition a peak is the Tm of can change anything on
 *  the signal: there are several transitions, the peak has one set by hand
 *  (which can be undone), its position has more than one counted peak, or it
 *  lies outside every transition's range. Never without a transition. A peak
 *  without an id is one that would be added at `value`. */
export function canUseAsTm(
  peak: Pick<MeltingStep, "well_id" | "value"> &
    Partial<Pick<MeltingStep, "id" | "assigned_window">>,
  analysis: Pick<MeltingAnalysis, "steps" | "outside_every_window">,
  channel: string | null,
  windows: readonly Range[],
): boolean {
  if (windows.length !== 1) return windows.length > 1;
  if (peak.assigned_window === windows[0].window) return true;
  const counted = analysis.steps.filter(
    (s) => s.well_id === peak.well_id && s.channel_key === channel && s.status !== "rejected",
  ).length;
  return peak.id === undefined
    ? counted > 0 || !inRange(peak.value, windows[0])
    : counted > 1 || analysis.outside_every_window.includes(peak.id);
}

/** What the plot's pick bar asks of the peak list: one of its forms, opened on
 *  the peak (or, to add, the position) with the value or window given, or its
 *  Accept. The list keeps the only forms and the only saves. */
export type StepRequest = {
  kind: "assign" | "correct" | "reject" | "add" | "accept";
  stepId?: string;
  wellId?: string;
  value?: string;
  /** Given when `value` is a found peak the click snapped to: the temperature
   *  clicked, which the form offers to put back. */
  clicked?: string;
  window?: string | null;
};

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

/** A form's title; `peak` reads "the peak at 68.4 °C on Capillary 8". */
const FORM_TITLES = {
  reject: (peak: string) => `Exclude ${peak}`,
  correct: (peak: string) => `Edit the temperature of ${peak}`,
  assign: (peak: string) => `Use ${peak} as Tm`,
  accepted: (peak: string) => `Mark ${peak} reviewed`,
  unreviewed: (peak: string) => `Unmark ${peak}`,
} as const;

function fmt(v: number): string {
  return formatMeasurementValue(v, 4);
}

/** A value field's text to two decimals, as the snap line says temperatures. */
const twoDecimals = (input: string) => Number(input).toFixed(2);

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
  windows: readonly Range[];
  /** The position being looked at and the lead window: where that position has
   *  several counted peaks in the window's range, the list says to pick one. */
  lookedAt?: string;
  lead?: Range;
  /** The x unit of the current signal. */
  unit: string;
  /** The value field of the open Add or Correct form; held by the parent so a
   *  plot click can fill it. */
  value: string;
  onValueChange: (value: string) => void;
  /** Taken once, then reported handled. */
  request: StepRequest | null;
  onRequestHandled: () => void;
  /** The peak picked on the plot; its row is highlighted. */
  pickedId: string | null;
  /** A peak added by hand was saved. */
  onAdded?: (step: MeltingStep) => void;
  /** Directly under the list of peaks. */
  underList?: ReactNode;
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
  lookedAt,
  lead,
  unit,
  value,
  onValueChange,
  request,
  onRequestHandled,
  pickedId,
  onAdded,
  underList,
  onReload,
}: MeltingStepsPanelProps) {
  const canEdit = useCanEdit();
  const editable = canEdit && !analysis.edit_refusal;
  const add = useAddMeltingStep(runId);
  const reviewStep = useReviewMeltingStep(runId);
  const assign = useAssignMeltingStep(runId);
  const [form, setForm] = useState<Form | null>(null);
  // The form opened on a found peak in place of the temperature clicked. Said
  // while that peak is still the field's value; typing ends it.
  const [snap, setSnap] = useState<{ to: string; clicked: string } | null>(null);
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
  // How many counted peaks the position looked at has in the lead window's
  // range, while none of them (and no peak for that window) is set by hand.
  const toPickFrom = (() => {
    if (!lead || !lookedAt) return 0;
    const counted = rows.filter((s) => s.well_id === lookedAt && s.status !== "rejected");
    const inside = counted.filter((s) => inRange(s.value, lead));
    const byHand = counted.some(
      (s) =>
        isWindow(s.assigned_window) && (s.assigned_window === lead.window || inside.includes(s)),
    );
    return byHand ? 0 : inside.length;
  })();
  const firstLookedAt = rows.find((s) => s.well_id === lookedAt)?.id;

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

  /** `clicked`: the temperature clicked, when `initialValue` is the found peak it snapped to. */
  const open = (next: Form, initialValue: string, clicked?: string) => {
    start();
    setForm(next);
    onValueChange(initialValue);
    setSnap(clicked === undefined ? null : { to: initialValue, clicked });
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
          ...(form.window ? { assigned_window: form.window } : {}),
        },
        {
          ...callbacks,
          onSuccess: (change) => {
            callbacks.onSuccess(change);
            onAdded?.(change.step);
          },
        },
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

  /** Opens on the window asked for, else on the step's own (a name that is no
   *  longer a window counts as none), else on the one whose range holds the
   *  peak, else the first. No window (by temperature range) is a choice only
   *  for a step that has one set by hand. The stored reason goes with the
   *  stored window only. */
  const openAssign = (s: MeltingStep, asked?: string | null) => {
    const own = isWindow(s.assigned_window) ? s.assigned_window : null;
    const start = own ?? (windows.find((w) => inRange(s.value, w)) ?? windows[0])?.window ?? null;
    const window = asked === undefined || (asked === null && own === null) ? start : asked;
    const stored = window !== null && window === s.assigned_window;
    open(
      { kind: "assign", step: s, window, reason: stored ? (s.assignment_reason ?? "") : "" },
      "",
    );
  };

  // biome-ignore lint/correctness/useExhaustiveDependencies: once per request; the peaks and forms are read as they are when it arrives.
  useEffect(() => {
    if (!request) return;
    onRequestHandled();
    // As for the list's own buttons, which are off during a save.
    if (!editable || busy) return;
    if (request.kind === "add") {
      const { wellId, window = null, value: at = "" } = request;
      if (wellId) open({ kind: "add", wellId, window, reason: "" }, at, request.clicked);
      return;
    }
    const s = analysis.steps.find((o) => o.id === request.stepId);
    if (!s) return;
    if (request.kind === "accept") setStatus(s, "accepted");
    else if (request.kind === "assign") openAssign(s, request.window);
    else {
      const initial = request.kind === "correct" ? (request.value ?? stepInput(s.value)) : "";
      open({ kind: request.kind, step: s, reason: s.reason ?? "" }, initial, request.clicked);
    }
  }, [request]);

  const formPosition = form && byWell.get(form.kind === "add" ? form.wellId : form.step.well_id);
  // A click that fills the field, or Use instrument value, replaces the peak snapped to.
  const snapped =
    snap && (form?.kind === "add" || form?.kind === "correct") && value === snap.to ? snap : null;
  // One peak per position and window: saving takes the window from the peak that has it.
  const naming =
    form?.kind === "assign"
      ? { id: form.step.id, wellId: form.step.well_id, window: form.window }
      : form?.kind === "add"
        ? { id: null, wellId: form.wellId, window: form.window }
        : null;
  const replaced = naming?.window
    ? analysis.steps.find(
        (o) =>
          o.id !== naming.id &&
          o.well_id === naming.wellId &&
          o.channel_key === channel &&
          o.assigned_window === naming.window,
      )
    : undefined;

  // Rejecting one of a position's two counted peaks leaves one, which a window
  // may then take as the Tm. A hint only: the server names the peaks.
  const leftAlone = (() => {
    if (form?.kind !== "reject" || windows.length === 0) return undefined;
    const counted = analysis.steps.filter(
      (o) =>
        o.well_id === form.step.well_id && o.channel_key === channel && o.status !== "rejected",
    );
    return counted.length === 2 && counted.some((o) => o.id === form.step.id)
      ? counted.find((o) => o.id !== form.step.id)
      : undefined;
  })();

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
            onClick={() =>
              open({ kind: "add", wellId: positions[0].well_id, window: null, reason: "" }, "")
            }
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
          rows.flatMap((s) => {
            const rejected = s.status === "rejected";
            const p = byWell.get(s.well_id);
            return [
              toPickFrom > 1 && s.id === firstLookedAt && (
                <li key="to-pick-from" className="px-2 py-1 text-xs text-muted-foreground">
                  {`${toPickFrom} peaks here. Pick the one to use as Tm.`}
                </li>
              ),
              <li
                key={s.id}
                data-picked={s.id === pickedId || undefined}
                className={cn(
                  "space-y-0.5 px-2 py-1.5",
                  s.id === pickedId && "bg-primary/10",
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
                    {peakKind(s)}
                  </Badge>
                  {s.instrument_value !== null && s.instrument_value !== s.value && (
                    <span className="text-xs text-muted-foreground">{`was ${fmt(s.instrument_value)}`}</span>
                  )}
                  {s.assigned_window &&
                    (isWindow(s.assigned_window) ? (
                      <Badge variant="secondary" className="no-underline">
                        {`Used as Tm (${s.assigned_window})`}
                      </Badge>
                    ) : (
                      <span className="flex items-center gap-x-1 text-xs text-muted-foreground no-underline">
                        {`Set as Tm of '${s.assigned_window}', which is no longer a transition on this signal`}
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
                          Mark reviewed
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
                          Unmark
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
                          Exclude
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
                        Edit temperature
                      </Button>
                      {canUseAsTm(s, analysis, channel, windows) && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          disabled={busy}
                          onClick={() => openAssign(s)}
                        >
                          Use as Tm
                        </Button>
                      )}
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
              </li>,
            ];
          })
        )}
      </ul>
      {underList}

      {form && editable && (
        <div className="space-y-3 rounded-md border p-3">
          <p className="text-sm font-medium">
            {form.kind === "add"
              ? "Add a peak"
              : FORM_TITLES[form.kind === "restore" ? form.status : form.kind](
                  `the peak at ${fmt(form.step.value)} ${unit} on ${formPosition?.position_label ?? "this position"}`,
                )}
          </p>
          {form.kind === "restore" && (
            <p className="text-xs text-muted-foreground">
              The reason below was given when the peak was excluded. Clear it or change it if it no
              longer applies.
            </p>
          )}
          {leftAlone && (
            <p className="text-xs text-muted-foreground">
              {`The other peak, at ${fmt(leftAlone.value)} ${unit}, may then be read as this position's Tm. Exclude it too if it is not a real transition.`}
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
                    onChange={(e) => {
                      setSnap(null);
                      onValueChange(e.target.value);
                    }}
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
            {(form.kind === "assign" || (form.kind === "add" && windows.length > 0)) && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`${ids}-window`}>Transition</Label>
                <Select
                  value={form.window ?? BY_TEMPERATURE}
                  onValueChange={(v) => {
                    const window = v === BY_TEMPERATURE ? null : v;
                    // An untouched stored reason explained the assignment being given up.
                    const givenUp =
                      form.kind === "assign" && form.reason === (form.step.assignment_reason ?? "");
                    setForm({ ...form, window, reason: givenUp ? "" : form.reason });
                  }}
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
                    {/* Undoes a choice made by hand; a new peak may be left to its temperature. */}
                    {(form.kind === "add" || isWindow(form.step.assigned_window)) && (
                      <SelectItem value={BY_TEMPERATURE}>By temperature range</SelectItem>
                    )}
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
          {snapped && (
            <p className="text-xs text-muted-foreground">
              {`Snapped to the peak of the derivative at ${twoDecimals(snapped.to)} ${unit}. You clicked ${twoDecimals(snapped.clicked)} ${unit}: `}
              <Button
                type="button"
                variant="link"
                className="h-auto p-0 text-xs font-normal"
                onClick={() => {
                  onValueChange(snapped.clicked);
                  setSnap(null);
                }}
              >
                use that
              </Button>
              .
            </p>
          )}
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
