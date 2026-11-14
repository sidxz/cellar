"use client";

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
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { ApiError } from "@/shared/lib/api/custom-instance";
import type { AddTemperatureWindowRequest } from "@/shared/lib/api/model";
import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useCurvePositions } from "../hooks/use-curve-positions";
import { useAddTemperatureWindow } from "../hooks/use-protocols";
import type { MeltConfig, ReadoutDefinition } from "../types";
import { Segmented } from "./segmented";

const NO_FILTER = {};

/** The server's own sentence when it sent one. */
function errorText(error: Error): string {
  const body = error instanceof ApiError ? (error.body as { message?: unknown } | null) : null;
  return typeof body?.message === "string" ? body.message : error.message;
}

type Measure = AddTemperatureWindowRequest["measures"][number];
const NEW = "__new__";

/** Positive finite number from a field, else NaN. */
const positive = (text: string) => {
  const n = text.trim() === "" ? Number.NaN : Number(text);
  return Number.isFinite(n) && n > 0 ? n : Number.NaN;
};

interface WindowShape {
  window: string;
  channel_key: string;
  low: number;
  high: number;
}

interface TemperatureWindowDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  protocolId: string;
  /** The protocol's readouts: existing windows and what each already measures. */
  readoutDefinitions: readonly ReadoutDefinition[];
  /** The protocol's dose unit, as shown (µM). */
  doseUnit: string;
}

/** Add a temperature window, or add values to one the protocol has: Tm and ΔTm
 *  per position, and descriptive series values per batch (no fit). */
export function TemperatureWindowDialog({
  open,
  onOpenChange,
  protocolId,
  readoutDefinitions,
  doseUnit,
}: TemperatureWindowDialogProps) {
  const [target, setTarget] = useState(NEW);
  const [name, setName] = useState("");
  const [channelKey, setChannelKey] = useState("");
  const [low, setLow] = useState("");
  const [high, setHigh] = useState("");
  const [tm, setTm] = useState(true);
  const [deltaTm, setDeltaTm] = useState(true);
  const [max, setMax] = useState(false);
  const [lowest, setLowest] = useState(false);
  const [threshold, setThreshold] = useState("2");
  const [at, setAt] = useState(false);
  const [concentration, setConcentration] = useState("");
  const add = useAddTemperatureWindow(protocolId);
  const { data } = useCurvePositions(protocolId, NO_FILTER, open);
  const { reset } = add;

  // Each opening starts a new window, not the last one's leftovers.
  useEffect(() => {
    if (!open) return;
    setTarget(NEW);
    setName("");
    setChannelKey("");
    setLow("");
    setHigh("");
    setTm(true);
    setDeltaTm(true);
    setMax(false);
    setLowest(false);
    setThreshold("2");
    setAt(false);
    setConcentration("");
    reset();
  }, [open, reset]);

  // Runs share channels; list each signal once.
  const channels = useMemo(() => {
    const byKey = new Map<string, string>();
    for (const run of data?.runs ?? []) {
      for (const c of run.channels) if (!byKey.has(c.key)) byKey.set(c.key, c.label);
    }
    return [...byKey].map(([key, label]) => ({ key, label }));
  }, [data]);

  // The protocol's windows and the values each already has.
  const windows = useMemo(() => {
    const byName = new Map<string, WindowShape & { has: MeltConfig[] }>();
    for (const rd of readoutDefinitions) {
      const mc = rd.melt_config;
      if (!mc) continue;
      const w = byName.get(mc.window) ?? { ...mc, has: [] };
      w.has.push(mc);
      byName.set(mc.window, w);
    }
    return [...byName.values()];
  }, [readoutDefinitions]);
  const existing = windows.find((w) => w.window === target) ?? null;

  const chooseTarget = (next: string) => {
    setTarget(next);
    const w = windows.find((x) => x.window === next);
    setName(w?.window ?? "");
    setChannelKey(w?.channel_key ?? "");
    setLow(w ? String(w.low) : "");
    setHigh(w ? String(w.high) : "");
    // On an existing window only new values are added; Tm/ΔTm start as it has them.
    setTm(!w);
    setDeltaTm(!w);
  };

  const thresholdN = positive(threshold);
  const concentrationN = positive(concentration);
  const has = (measure: Measure, param: number | null = null) =>
    !!existing?.has.some(
      (mc) =>
        mc.measure === measure &&
        (mc.threshold ?? null) === (measure === "lowest_shift_concentration" ? param : null) &&
        (mc.concentration ?? null) === (measure === "delta_tm_at_concentration" ? param : null),
    );
  const hasTm = has("tm");
  const hasDelta = has("delta_tm");
  const hasMax = has("max_delta_tm");
  const hasLowest = lowest && has("lowest_shift_concentration", thresholdN);
  const hasAt = at && has("delta_tm_at_concentration", concentrationN);

  const measures: Measure[] = [
    ...(tm && !hasTm ? (["tm"] as const) : []),
    ...(deltaTm && !hasDelta ? (["delta_tm"] as const) : []),
    ...(max && !hasMax ? (["max_delta_tm"] as const) : []),
    ...(lowest && !hasLowest ? (["lowest_shift_concentration"] as const) : []),
    ...(at && !hasAt ? (["delta_tm_at_concentration"] as const) : []),
  ];

  const lowN = low.trim() === "" ? Number.NaN : Number(low);
  const highN = high.trim() === "" ? Number.NaN : Number(high);
  const boundsInverted = lowN >= highN; // false while either is empty
  const canSave =
    name.trim() !== "" &&
    channelKey !== "" &&
    lowN < highN && // false for NaN
    measures.length > 0 &&
    !(lowest && Number.isNaN(thresholdN)) &&
    !(at && Number.isNaN(concentrationN)) &&
    !hasLowest &&
    !hasAt &&
    !add.isPending;

  const submit = () => {
    if (!canSave) return;
    add.mutate(
      {
        window: name.trim(),
        channel_key: channelKey,
        low: lowN,
        high: highN,
        measures,
        ...(measures.includes("lowest_shift_concentration")
          ? { lowest_shift_threshold: thresholdN }
          : {}),
        ...(measures.includes("delta_tm_at_concentration")
          ? { delta_tm_at_concentration: concentrationN }
          : {}),
      },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  const fixed = !!existing;
  const tick = (
    id: string,
    label: string,
    checked: boolean,
    onChange: (v: boolean) => void,
    already = false,
  ) => (
    <div className="flex items-center gap-2">
      <Checkbox
        id={id}
        checked={checked || already}
        disabled={already}
        onCheckedChange={(v) => onChange(v === true)}
      />
      <Label htmlFor={id}>{label}</Label>
    </div>
  );

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && add.isPending) return;
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add temperature window</DialogTitle>
          <DialogDescription>
            Adds readouts computed from each position's melting steps inside the window.
          </DialogDescription>
        </DialogHeader>

        {channels.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Import a run with traces first; the window's signal comes from its traces.
          </p>
        ) : (
          <div className="grid gap-4 py-2">
            {windows.length > 0 && (
              <Segmented
                label="Window"
                value={target}
                options={[
                  { value: NEW, label: "New window" },
                  ...windows.map((w) => ({ value: w.window, label: w.window })),
                ]}
                onChange={chooseTarget}
              />
            )}
            <div className="grid gap-2">
              <Label htmlFor="tw-name">Name</Label>
              <Input
                id="tw-name"
                value={name}
                maxLength={60}
                disabled={fixed}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Main"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="tw-signal">Signal</Label>
              <Select value={channelKey} onValueChange={setChannelKey} disabled={fixed}>
                <SelectTrigger id="tw-signal">
                  <SelectValue placeholder="Select signal..." />
                </SelectTrigger>
                <SelectContent>
                  {channels.map((c) => (
                    <SelectItem key={c.key} value={c.key}>
                      {c.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-2">
                <Label htmlFor="tw-low">Low (°C)</Label>
                <Input
                  id="tw-low"
                  type="number"
                  value={low}
                  disabled={fixed}
                  onChange={(e) => setLow(e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="tw-high">High (°C)</Label>
                <Input
                  id="tw-high"
                  type="number"
                  value={high}
                  disabled={fixed}
                  onChange={(e) => setHigh(e.target.value)}
                />
              </div>
              {boundsInverted && (
                <p className="col-span-2 text-destructive text-sm">Low must be below High.</p>
              )}
            </div>
            <div className="flex items-center gap-6">
              {tick("tw-tm", "Tm", tm, setTm, hasTm)}
              {tick("tw-dtm", "ΔTm", deltaTm, setDeltaTm, hasDelta)}
            </div>
            <fieldset className="grid gap-2">
              <legend className="mb-1 text-sm font-medium">
                Series values{" "}
                <span className="font-normal text-muted-foreground">
                  (descriptive, per batch; no fit)
                </span>
              </legend>
              {tick("tw-max", "Max ΔTm", max, setMax, hasMax)}
              <div className="flex flex-wrap items-center gap-2">
                {tick("tw-lowest", "Lowest shifting concentration", lowest, setLowest)}
                <span className="text-sm text-muted-foreground">ΔTm outside ±</span>
                <Input
                  aria-label="Shift threshold (°C)"
                  type="number"
                  min={0}
                  step={0.5}
                  className="h-8 w-16"
                  value={threshold}
                  disabled={!lowest}
                  onChange={(e) => setThreshold(e.target.value)}
                />
                <span className="text-sm text-muted-foreground">°C</span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {tick("tw-at", "ΔTm at a stated concentration", at, setAt)}
                <Input
                  aria-label={`Concentration (${doseUnit})`}
                  type="number"
                  min={0}
                  className="h-8 w-20"
                  value={concentration}
                  disabled={!at}
                  onChange={(e) => setConcentration(e.target.value)}
                />
                <span className="text-sm text-muted-foreground">{doseUnit}</span>
              </div>
              {(hasLowest || hasAt) && (
                <p className="text-sm text-muted-foreground">This window already has it.</p>
              )}
            </fieldset>
            {add.error && (
              <p role="alert" className="text-destructive text-sm">
                {errorText(add.error)}
              </p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={add.isPending}>
            Cancel
          </Button>
          {channels.length > 0 && (
            <Button onClick={submit} disabled={!canSave}>
              {add.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {fixed ? "Add values" : "Add window"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
