"use client";

import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import { type ComponentProps, type ReactNode, useRef, useState } from "react";
import { column } from "../../lib/dataset";
import { type OverlayKind, overlayOptions } from "../../lib/overlays/options";
import { useWorkbench } from "../../store/workbench-context";
import type { OverlayConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";

/** The numbers in ``text``, comma or space separated; anything else is dropped. */
export function parseNumberList(text: string): number[] {
  return text
    .split(/[\s,]+/)
    .filter(Boolean)
    .map(Number)
    .filter(Number.isFinite);
}

type Limits = OverlayConfig["limits"];

/** The overlays a plot can draw over ``ds``: kinds it cannot draw here are left out, those
 * it cannot draw yet show disabled with the reason. Every change is one ``updatePanel`` (one
 * undo step); typed values commit when the input is left or on Enter and start empty — no
 * value is ever suggested. */
export function OverlaySection({ ds, panelId }: { ds: Dataset; panelId: string }) {
  const panel = useWorkbench((s) => s.panels.find((p) => p.id === panelId));
  const updatePanel = useWorkbench((s) => s.updatePanel);
  if (!panel) return null;
  const options = overlayOptions(ds, panel);
  if (Object.keys(options).length === 0) return null;

  const o = panel.overlays ?? {};
  const set = (patch: OverlayConfig) => updatePanel(panelId, { overlays: { ...o, ...patch } });
  const id = (field: string) => `${panelId}-overlay-${field}`;
  /** The reason ``kind`` cannot be drawn yet, if it cannot. */
  const reason = (kind: OverlayKind) =>
    typeof options[kind] === "string" ? (options[kind] as string) : undefined;
  const unit = panel.y ? column(ds, panel.y)?.unit : null;

  return (
    <section className="space-y-3">
      <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        Overlays
      </h3>

      {options.bands && (
        <Toggle
          id={id("bands")}
          label="Control bands (mean ± 3 SD)"
          checked={o.bands}
          reason={reason("bands")}
          onChange={(bands) => set({ bands: bands || undefined })}
        />
      )}

      {(options.driftBand || options.trend) && (
        <Choice
          id={id("drift")}
          label="Drift"
          value={o.drift ?? "none"}
          options={[
            { value: "none", label: "None" },
            ...(options.driftBand
              ? [{ value: "band", label: "Band per plate row/column", reason: reason("driftBand") }]
              : []),
            ...(options.trend
              ? [{ value: "trend", label: "Trend line", reason: reason("trend") }]
              : []),
          ]}
          onChange={(v) => set({ drift: v === "none" ? undefined : (v as "band" | "trend") })}
        />
      )}

      {options.zPrime && (
        <Toggle
          id={id("zPrime")}
          label="Z′ per plate (stored)"
          checked={o.zPrime}
          reason={reason("zPrime")}
          onChange={(zPrime) => set({ zPrime: zPrime || undefined })}
        />
      )}

      {options.refLine && (
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Label htmlFor={id("refLine")} className="text-xs font-normal">
              Reference line
            </Label>
            <CommitInput
              id={id("refLine")}
              type="number"
              step="any"
              value={o.refLine === undefined ? "" : String(o.refLine)}
              disabled={Boolean(reason("refLine"))}
              aria-describedby={[unit && id("refLine-unit"), id("refLine-note")]
                .filter(Boolean)
                .join(" ")}
              onCommit={(text) => {
                const v = text === "" ? undefined : Number(text);
                if (v !== o.refLine && (v === undefined || Number.isFinite(v))) {
                  set({ refLine: v });
                }
              }}
            />
            {unit && (
              <span id={id("refLine-unit")} className="text-xs text-muted-foreground">
                {unit}
              </span>
            )}
          </div>
          <Hint id={id("refLine-note")}>
            {reason("refLine") ?? "Display only — hit criteria are unchanged"}
          </Hint>
        </div>
      )}

      {options.limits && (
        <LimitsControl
          id={id("limits")}
          limits={o.limits}
          reason={reason("limits")}
          onChange={(limits) => set({ limits })}
        />
      )}

      {(["lipe", "selectivity"] as const).map(
        (kind) =>
          options[kind] && (
            <NumberList
              key={kind}
              id={id(kind)}
              label={kind === "lipe" ? "LipE guides" : "Selectivity folds"}
              placeholder={kind === "lipe" ? "e.g. 3, 5" : "e.g. 10, 100"}
              values={o[kind]}
              reason={reason(kind)}
              onChange={(values) => set({ [kind]: values })}
            />
          ),
      )}
    </section>
  );
}

/** A list of values typed comma or space separated (LipE values, selectivity folds); an
 * unchanged list commits nothing, an empty one turns the overlay off. */
function NumberList({
  id,
  label,
  placeholder,
  values = [],
  reason,
  onChange,
}: {
  id: string;
  label: string;
  placeholder: string;
  values?: number[];
  reason?: string;
  onChange: (values: number[] | undefined) => void;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <Label htmlFor={id} className="text-xs font-normal">
          {label}
        </Label>
        <CommitInput
          id={id}
          placeholder={placeholder}
          value={values.join(", ")}
          disabled={Boolean(reason)}
          aria-describedby={reason ? `${id}-reason` : undefined}
          onCommit={(text) => {
            const next = parseNumberList(text);
            if (next.join() !== values.join()) onChange(next.length ? next : undefined);
          }}
        />
      </div>
      {reason && <Hint id={`${id}-reason`}>{reason}</Hint>}
    </div>
  );
}

function Hint({ id, children }: { id: string; children: ReactNode }) {
  return (
    <p id={id} className="pl-6 text-xs text-muted-foreground">
      {children}
    </p>
  );
}

/** An on/off overlay; disabled with ``reason`` when it cannot be drawn yet. */
function Toggle({
  id,
  label,
  checked,
  reason,
  onChange,
}: {
  id: string;
  label: string;
  checked?: boolean;
  reason?: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <Checkbox
          id={id}
          checked={Boolean(checked)}
          disabled={Boolean(reason)}
          aria-describedby={reason ? `${id}-reason` : undefined}
          onCheckedChange={(v) => onChange(v === true)}
        />
        <Label htmlFor={id} className="text-xs font-normal">
          {label}
        </Label>
      </div>
      {reason && <Hint id={`${id}-reason`}>{reason}</Hint>}
    </div>
  );
}

/** A labeled radio group; an option (or the whole group) is disabled with its reason. */
function Choice({
  id,
  label,
  value,
  options,
  reason,
  onChange,
  children,
}: {
  id: string;
  label: string;
  value: string;
  options: { value: string; label: string; reason?: string }[];
  reason?: string;
  onChange: (value: string) => void;
  children?: ReactNode;
}) {
  return (
    <div className="space-y-1">
      <p id={id} className="text-xs">
        {label}
      </p>
      <RadioGroup
        className="gap-1"
        aria-labelledby={id}
        aria-describedby={reason ? `${id}-reason` : undefined}
        disabled={Boolean(reason)}
        value={value}
        onValueChange={onChange}
      >
        {options.map((opt) => {
          const itemId = `${id}-${opt.value}`;
          return (
            <div key={opt.value}>
              <div className="flex items-center gap-2 pl-2">
                <RadioGroupItem
                  id={itemId}
                  value={opt.value}
                  disabled={Boolean(opt.reason)}
                  aria-describedby={opt.reason ? `${itemId}-reason` : undefined}
                />
                <Label htmlFor={itemId} className="text-xs font-normal">
                  {opt.label}
                </Label>
              </div>
              {opt.reason && <Hint id={`${itemId}-reason`}>{opt.reason}</Hint>}
            </div>
          );
        })}
      </RadioGroup>
      {reason && <Hint id={`${id}-reason`}>{reason}</Hint>}
      {children}
    </div>
  );
}

/** Control limits: off, from the plotted points, or entered. Picking "Entered" keeps what is
 * drawn until both limits are typed and Lower is below Upper; clearing both turns them off. */
function LimitsControl({
  id,
  limits,
  reason,
  onChange,
}: {
  id: string;
  limits: Limits;
  reason?: string;
  onChange: (limits: Limits) => void;
}) {
  const [entering, setEntering] = useState(false);
  const [invalid, setInvalid] = useState(false);
  // A stored change (commit or undo) ends any half-entered limits.
  const [seen, setSeen] = useState(limits);
  if (seen !== limits) {
    setSeen(limits);
    setEntering(false);
    setInvalid(false);
  }
  const lower = useRef<HTMLInputElement>(null);
  const upper = useRef<HTMLInputElement>(null);
  const entered = limits?.mode === "entered" ? limits : undefined;
  const mode = entering ? "entered" : (limits?.mode ?? "off");

  const commitEntered = () => {
    const lo = lower.current?.value.trim() ?? "";
    const hi = upper.current?.value.trim() ?? "";
    if (lo === "" && hi === "") {
      setInvalid(false);
      if (entered) onChange(undefined);
      return;
    }
    if (lo === "" || hi === "") return;
    const [l, u] = [Number(lo), Number(hi)];
    setInvalid(l >= u);
    if (l < u && (l !== entered?.lower || u !== entered?.upper)) {
      onChange({ mode: "entered", lower: l, upper: u });
    }
  };
  const errorId = `${id}-error`;
  const bound = (name: "Lower" | "Upper", ref: typeof lower, value?: number) => (
    <div className="flex items-center gap-2">
      <Label htmlFor={`${id}-${name}`} className="w-10 text-xs font-normal">
        {name}
      </Label>
      <CommitInput
        ref={ref}
        id={`${id}-${name}`}
        type="number"
        step="any"
        value={value === undefined ? "" : String(value)}
        aria-invalid={invalid || undefined}
        aria-describedby={invalid ? errorId : undefined}
        onCommit={commitEntered}
      />
    </div>
  );

  return (
    <Choice
      id={id}
      label="Control limits"
      value={mode}
      reason={reason}
      options={[
        { value: "off", label: "Off" },
        { value: "plotted", label: "From plotted points" },
        { value: "entered", label: "Entered" },
      ]}
      onChange={(next) => {
        setEntering(next === "entered" && !entered);
        if (next === "plotted" && limits?.mode !== "plotted") onChange({ mode: "plotted" });
        if (next === "off" && limits) onChange(undefined);
      }}
    >
      {mode === "entered" && (
        <div className="space-y-1 pl-6">
          {bound("Lower", lower, entered?.lower)}
          {bound("Upper", upper, entered?.upper)}
          {invalid && (
            <p id={errorId} role="alert" className="text-xs text-destructive">
              Lower must be below Upper
            </p>
          )}
        </div>
      )}
    </Choice>
  );
}

/** An input that commits once, when left or on Enter — never per keystroke. A new ``value``
 * from outside (commit, undo) replaces what it shows. */
function CommitInput({
  value,
  onCommit,
  ...props
}: { value: string; onCommit: (text: string) => void } & Omit<
  ComponentProps<typeof Input>,
  "value" | "defaultValue" | "onBlur" | "onKeyDown"
>) {
  return (
    <Input
      key={value}
      {...props}
      defaultValue={value}
      className="h-8 w-24"
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
      }}
      onBlur={(e) => {
        const input = e.currentTarget;
        // Unparseable number text reads as "": keep what was there instead of clearing it.
        if (input.validity.badInput) input.value = value;
        else onCommit(input.value.trim());
      }}
    />
  );
}
