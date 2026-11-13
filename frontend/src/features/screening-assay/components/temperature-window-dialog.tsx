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
import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useCurvePositions } from "../hooks/use-curve-positions";
import { useAddTemperatureWindow } from "../hooks/use-protocols";

const NO_FILTER = {};

/** The server's own sentence when it sent one. */
function errorText(error: Error): string {
  const body = error instanceof ApiError ? (error.body as { message?: unknown } | null) : null;
  return typeof body?.message === "string" ? body.message : error.message;
}

interface TemperatureWindowDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  protocolId: string;
}

/** Add a temperature window: Tm and/or ΔTm readouts computed from melting steps. */
export function TemperatureWindowDialog({
  open,
  onOpenChange,
  protocolId,
}: TemperatureWindowDialogProps) {
  const [name, setName] = useState("");
  const [channelKey, setChannelKey] = useState("");
  const [low, setLow] = useState("");
  const [high, setHigh] = useState("");
  const [tm, setTm] = useState(true);
  const [deltaTm, setDeltaTm] = useState(true);
  const add = useAddTemperatureWindow(protocolId);
  const { data } = useCurvePositions(protocolId, NO_FILTER, open);
  const { reset } = add;

  // Each opening starts a new window, not the last one's leftovers.
  useEffect(() => {
    if (!open) return;
    setName("");
    setChannelKey("");
    setLow("");
    setHigh("");
    setTm(true);
    setDeltaTm(true);
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

  const lowN = low.trim() === "" ? Number.NaN : Number(low);
  const highN = high.trim() === "" ? Number.NaN : Number(high);
  const boundsInverted = lowN >= highN; // false while either is empty
  const canSave =
    name.trim() !== "" &&
    channelKey !== "" &&
    lowN < highN && // false for NaN
    (tm || deltaTm) &&
    !add.isPending;

  const submit = () => {
    if (!canSave) return;
    add.mutate(
      {
        window: name.trim(),
        channel_key: channelKey,
        low: lowN,
        high: highN,
        measures: [...(tm ? (["tm"] as const) : []), ...(deltaTm ? (["delta_tm"] as const) : [])],
      },
      { onSuccess: () => onOpenChange(false) },
    );
  };

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
            <div className="grid gap-2">
              <Label htmlFor="tw-name">Name</Label>
              <Input
                id="tw-name"
                value={name}
                maxLength={60}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Main"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="tw-signal">Signal</Label>
              <Select value={channelKey} onValueChange={setChannelKey}>
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
                  onChange={(e) => setLow(e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="tw-high">High (°C)</Label>
                <Input
                  id="tw-high"
                  type="number"
                  value={high}
                  onChange={(e) => setHigh(e.target.value)}
                />
              </div>
              {boundsInverted && (
                <p className="col-span-2 text-destructive text-sm">Low must be below High.</p>
              )}
            </div>
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <Checkbox id="tw-tm" checked={tm} onCheckedChange={(v) => setTm(v === true)} />
                <Label htmlFor="tw-tm">Tm</Label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="tw-dtm"
                  checked={deltaTm}
                  onCheckedChange={(v) => setDeltaTm(v === true)}
                />
                <Label htmlFor="tw-dtm">ΔTm</Label>
              </div>
            </div>
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
              Add window
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
