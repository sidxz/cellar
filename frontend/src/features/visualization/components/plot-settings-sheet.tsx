"use client";

import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Slider } from "@/shared/components/ui/slider";
import { cn } from "@/shared/lib/utils";
import { Plus, X } from "lucide-react";
import { Fragment, type ReactNode, useEffect } from "react";
import { colorBins, numericRange } from "../lib/appearance";
import { column } from "../lib/dataset";
import { numericValueColumn, retypePanel } from "../lib/default-panels";
import { MAX_CATEGORIES, levels } from "../lib/traces/common";
import { useWorkbench } from "../store/workbench-context";
import type { Appearance, PanelConfig, PanelPatch, PanelType } from "../store/workbench-store";
import type { Dataset, DatasetColumn } from "../types";
import { FieldSelect } from "./field-select";
import { type EditField, panelTitle } from "./panels/panel-frame";

type Kind = DatasetColumn["kind"];
const NUMBER: Kind[] = ["number"];
const CATEGORY: Kind[] = ["category"];
const COLOR: Kind[] = ["number", "category"];
const TOOLTIP: Kind[] = ["number", "category", "text"];

const TYPES: { value: PanelType; label: string; numeric: boolean }[] = [
  { value: "scatter", label: "Scatter", numeric: true },
  { value: "histogram", label: "Histogram", numeric: true },
  { value: "bar", label: "Bar", numeric: false },
  { value: "box", label: "Box", numeric: true },
];

/** Why a field cannot group bars or boxes: more values than one bar or box each. */
function tooManyGroups(ds: Dataset, key: string): string | undefined {
  const n = levels(ds, key).length;
  if (n <= MAX_CATEGORIES) return undefined;
  return `${n.toLocaleString()} values; at most ${MAX_CATEGORIES.toLocaleString()} groups can be shown`;
}

/** The plot editor: Data, Appearance and Tooltip settings of one panel, shown in place of
 * the filter rail so the plot stays in view and redraws as settings change. Every change
 * is one ``updatePanel`` (one undo step); typed numbers commit when the input is left. */
export function PlotSettingsSheet({
  ds,
  panelId,
  focusField,
  onClose,
}: {
  ds: Dataset;
  panelId: string;
  /** The control to focus: the header chip that opened the editor. */
  focusField?: EditField;
  onClose: () => void;
}) {
  const panel = useWorkbench((s) => s.panels.find((p) => p.id === panelId));
  const updatePanel = useWorkbench((s) => s.updatePanel);

  // The panel can go away under the editor (closed, or its adding undone).
  useEffect(() => {
    if (!panel) onClose();
  }, [panel, onClose]);

  useEffect(() => {
    if (focusField) document.getElementById(`${panelId}-${focusField}`)?.focus();
  }, [panelId, focusField]);

  if (!panel) return null;
  const p: PanelConfig = panel;
  const a = p.appearance;
  const set = (patch: PanelPatch) => updatePanel(p.id, patch);
  const look = (patch: Partial<Appearance>) => set({ appearance: patch });
  const id = (field: string) => `${p.id}-${field}`;
  const firstNumeric = numericValueColumn(ds)?.key;
  const agg = p.agg ?? "count";
  const colorIsNumber = a.colorBy ? column(ds, a.colorBy)?.kind === "number" : false;
  const showY = p.type === "scatter" || p.type === "box" || (p.type === "bar" && agg !== "count");

  return (
    <div
      className="flex h-full min-h-0 flex-col"
      onKeyDown={(e) => {
        // Popovers inside handle (and mark) their own Escape first.
        if (e.key === "Escape" && !e.defaultPrevented) onClose();
      }}
    >
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <h2 className="min-w-0 flex-1 truncate text-sm font-semibold">
          Edit plot · {panelTitle(ds, p)}
        </h2>
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7"
          aria-label="Close plot editor"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-auto px-3 py-2">
        <p className="text-xs text-muted-foreground">Changes apply live; Undo reverts them.</p>

        <Section title="Data">
          <Segmented
            label="Plot type"
            className="grid w-full grid-cols-4"
            value={p.type}
            options={TYPES.map((t) => ({ ...t, disabled: t.numeric && !firstNumeric }))}
            onChange={(type) => set(retypePanel(ds, p, type))}
          />
          {(p.type === "scatter" || p.type === "histogram") && (
            <Row label="X" htmlFor={id("x")}>
              <FieldSelect
                id={id("x")}
                ds={ds}
                kinds={NUMBER}
                value={p.x}
                onChange={(x) => set({ x })}
              />
            </Row>
          )}
          {p.type === "scatter" && (
            <Toggle
              id={id("logX")}
              label="Log X"
              checked={p.logX}
              onChange={(logX) => set({ logX })}
            />
          )}
          {(p.type === "bar" || p.type === "box") && (
            <Row label="Group" htmlFor={id("category")}>
              <FieldSelect
                id={id("category")}
                ds={ds}
                kinds={CATEGORY}
                value={p.category}
                onChange={(category) => set({ category })}
                disabledReason={(c) => tooManyGroups(ds, c.key)}
              />
            </Row>
          )}
          {p.type === "bar" && (
            <Row label="Measure">
              <Segmented
                label="Measure"
                value={agg}
                options={[
                  { value: "count", label: "Count" },
                  { value: "mean", label: "Mean", disabled: !firstNumeric },
                  { value: "median", label: "Median", disabled: !firstNumeric },
                ]}
                onChange={(next) => set({ agg: next, y: p.y ?? firstNumeric })}
              />
            </Row>
          )}
          {showY && (
            <Row label="Y" htmlFor={id("y")}>
              <FieldSelect
                id={id("y")}
                ds={ds}
                kinds={NUMBER}
                value={p.y}
                onChange={(y) => set({ y })}
              />
            </Row>
          )}
          {p.type !== "histogram" && (
            <Toggle
              id={id("logY")}
              label="Log Y"
              checked={p.logY}
              onChange={(logY) => set({ logY })}
            />
          )}
          {p.type === "histogram" && (
            <Row label="Bins" htmlFor={id("bins")}>
              <NumberInput
                id={id("bins")}
                value={p.bins ?? 30}
                min={2}
                max={200}
                integer
                onCommit={(bins) => set({ bins })}
              />
            </Row>
          )}
          {p.type === "scatter" && (
            <Row label="Split by" htmlFor={id("splitBy")}>
              <FieldSelect
                id={id("splitBy")}
                ds={ds}
                kinds={CATEGORY}
                clearable
                value={a.splitBy}
                onChange={(splitBy) => look({ splitBy })}
              />
            </Row>
          )}
        </Section>

        {p.type === "histogram" && (
          <Section title="Appearance">
            <Row label="Stack by" htmlFor={id("colorBy")}>
              <FieldSelect
                id={id("colorBy")}
                ds={ds}
                kinds={CATEGORY}
                clearable
                value={colorIsNumber ? undefined : a.colorBy}
                onChange={(colorBy) => look({ colorBy, colorBins: undefined })}
              />
            </Row>
          </Section>
        )}

        {p.type === "scatter" && (
          <>
            <Section title="Appearance">
              <Row label="Color" htmlFor={id("colorBy")}>
                <FieldSelect
                  id={id("colorBy")}
                  ds={ds}
                  kinds={COLOR}
                  clearable
                  value={a.colorBy}
                  // Cut-offs belong to the field they were set for.
                  onChange={(colorBy) => look({ colorBy, colorBins: undefined })}
                />
              </Row>
              {a.colorBy && colorIsNumber && (
                <>
                  <Row label="Scale">
                    <Segmented
                      label="Color scale"
                      value={a.colorMode}
                      options={[
                        { value: "range", label: "Range" },
                        { value: "bins", label: "Bins" },
                      ]}
                      onChange={(colorMode) => look({ colorMode })}
                    />
                  </Row>
                  {a.colorMode === "bins" && (
                    <BinsEditor
                      ds={ds}
                      colorKey={a.colorBy}
                      cuts={a.colorBins}
                      onChange={(colorBins) => look({ colorBins })}
                    />
                  )}
                </>
              )}
              <Row label="Shape" htmlFor={id("shapeBy")}>
                <FieldSelect
                  id={id("shapeBy")}
                  ds={ds}
                  kinds={CATEGORY}
                  clearable
                  value={a.shapeBy}
                  onChange={(shapeBy) => look({ shapeBy })}
                />
              </Row>
              <Row label="Size" htmlFor={id("sizeBy")}>
                <FieldSelect
                  id={id("sizeBy")}
                  ds={ds}
                  kinds={NUMBER}
                  clearable
                  placeholder="Auto (by point count)"
                  value={a.sizeBy}
                  onChange={(sizeBy) => look({ sizeBy })}
                />
              </Row>
              <Row label="Opacity">
                <div className="flex items-center gap-2">
                  {/* Uncontrolled while dragging; one commit on release. */}
                  <Slider
                    key={a.opacity}
                    defaultValue={[a.opacity]}
                    min={0.1}
                    max={1}
                    step={0.05}
                    thumbLabels={["Opacity"]}
                    onValueCommit={([opacity]) => look({ opacity })}
                  />
                  <span className="w-9 text-right text-xs tabular-nums text-muted-foreground">
                    {Math.round(a.opacity * 100)}%
                  </span>
                </div>
              </Row>
              <Toggle
                id={id("showFiltered")}
                label="Show filtered rows as faint ×"
                checked={a.showFiltered}
                onChange={(showFiltered) => look({ showFiltered })}
              />
            </Section>

            <Section title="Tooltip">
              {a.tooltip.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {a.tooltip.map((key) => {
                    const label = column(ds, key)?.label ?? key;
                    return (
                      <span
                        key={key}
                        className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs"
                      >
                        {label}
                        <button
                          type="button"
                          aria-label={`Remove ${label} from tooltip`}
                          className="text-muted-foreground hover:text-foreground"
                          onClick={() => look({ tooltip: a.tooltip.filter((k) => k !== key) })}
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    );
                  })}
                </div>
              )}
              <Row label="Add" htmlFor={id("tooltip")}>
                <FieldSelect
                  id={id("tooltip")}
                  ds={ds}
                  kinds={TOOLTIP}
                  placeholder="Add a field"
                  value={undefined}
                  onChange={(key) => {
                    if (key && !a.tooltip.includes(key)) look({ tooltip: [...a.tooltip, key] });
                  }}
                />
              </Row>
            </Section>
          </>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      {children}
    </section>
  );
}

/** A labeled control row: fixed label column, control filling the rest. */
function Row({
  label,
  htmlFor,
  children,
}: { label: string; htmlFor?: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[4.5rem_minmax(0,1fr)] items-center gap-2">
      {htmlFor ? (
        <Label htmlFor={htmlFor} className="text-xs font-normal text-muted-foreground">
          {label}
        </Label>
      ) : (
        <span className="text-xs text-muted-foreground">{label}</span>
      )}
      {children}
    </div>
  );
}

function Toggle({
  id,
  label,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  checked?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-2 pl-20">
      <Checkbox id={id} checked={Boolean(checked)} onCheckedChange={(v) => onChange(v === true)} />
      <Label htmlFor={id} className="text-xs font-normal">
        {label}
      </Label>
    </div>
  );
}

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  className,
}: {
  label: string;
  value: T;
  options: { value: T; label: string; disabled?: boolean }[];
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <fieldset
      aria-label={label}
      className={cn("inline-flex min-w-0 rounded-md border p-0.5", className)}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          disabled={o.disabled}
          className={cn(
            "rounded px-2 py-0.5 text-xs disabled:pointer-events-none disabled:opacity-50",
            o.value === value
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:bg-accent",
          )}
          onClick={() => {
            if (o.value !== value) onChange(o.value);
          }}
        >
          {o.label}
        </button>
      ))}
    </fieldset>
  );
}

/** A number input that commits once, when left or on Enter — never per keystroke.
 * Out-of-range or blank input snaps back. */
function NumberInput({
  id,
  value,
  onCommit,
  min = Number.NEGATIVE_INFINITY,
  max = Number.POSITIVE_INFINITY,
  integer = false,
  "aria-label": ariaLabel,
}: {
  id?: string;
  value: number;
  onCommit: (value: number) => void;
  min?: number;
  max?: number;
  integer?: boolean;
  "aria-label"?: string;
}) {
  return (
    <Input
      // A new value from outside (undo) replaces whatever the input shows.
      key={value}
      id={id}
      aria-label={ariaLabel}
      type="number"
      step={integer ? 1 : "any"}
      defaultValue={value}
      className="h-8 w-24"
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
      }}
      onBlur={(e) => {
        const raw = e.currentTarget.value.trim();
        let v = raw === "" ? Number.NaN : Number(raw);
        if (!Number.isFinite(v)) v = value;
        v = Math.min(max, Math.max(min, integer ? Math.round(v) : v));
        e.currentTarget.value = String(v);
        if (v !== value) onCommit(v);
      }}
    />
  );
}

/** Cut-offs of a binned numeric color: each bin's color and range, an input per cut-off,
 * add/remove (at least two bins stay). */
function BinsEditor({
  ds,
  colorKey,
  cuts,
  onChange,
}: {
  ds: Dataset;
  colorKey: string;
  cuts?: number[];
  onChange: (cuts: number[]) => void;
}) {
  const b = colorBins(ds, colorKey, cuts);
  const save = (next: number[]) => onChange([...next].sort((p, q) => p - q));
  const add = () => {
    const last = b.cuts.at(-1);
    const hi = numericRange(ds, colorKey)?.[1];
    if (last === undefined) save([hi ?? 0]);
    else save([...b.cuts, hi !== undefined && hi > last ? (last + hi) / 2 : last + 1]);
  };
  return (
    <div className="space-y-1 pl-20">
      {b.labels.map((label, k) => (
        <Fragment key={label}>
          <div className="flex items-center gap-2 text-xs">
            <span className="h-3 w-3 rounded-sm" style={{ backgroundColor: b.colors[k] }} />
            {label}
          </div>
          {k < b.cuts.length && (
            <div className="flex items-center gap-1">
              <NumberInput
                aria-label={`Cut-off ${k + 1}`}
                value={b.cuts[k]}
                onCommit={(v) => save(b.cuts.map((c, j) => (j === k ? v : c)))}
              />
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7"
                aria-label={`Remove cut-off ${k + 1}`}
                disabled={b.cuts.length < 2}
                onClick={() => save(b.cuts.filter((_, j) => j !== k))}
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
        </Fragment>
      ))}
      <Button size="sm" variant="ghost" className="h-7" onClick={add}>
        <Plus className="h-3.5 w-3.5" />
        Add bin
      </Button>
    </div>
  );
}
