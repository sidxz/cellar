"use client";

/**
 * The results grid's toolbar: a compound search, readout filters, sort, the column picker and
 * Maximize, with the applied search and filters as removable chips beneath. Search and filters
 * live in the campaign's filter state, so the bulk gestures act on exactly the rows shown.
 */

import { ArrowDownUp, Columns3, Filter, Maximize2, Minimize2, Plus, Search, X } from "lucide-react";
import { useId, useState } from "react";

import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";

import { QC_LABEL } from "../../lib/qc-verdicts";
import type { CampaignFilters, MeasurementFilter } from "../campaign-filter-bar";

/** A readout the toolbar can filter or sort by. */
export interface ReadoutOption {
  /** The channel id. */
  id: string;
  /** "Protocol · column", with the stage first when several stages show. */
  label: string;
  /** The unit its exact values are stored in; "" when it has none. */
  unit: string;
}

/** One column the viewer can show or hide. */
export interface ColumnChoice {
  id: string;
  label: string;
  /** Holds no value anywhere at its stage. */
  empty?: boolean;
}

export interface ColumnGroup {
  title: string;
  columns: ColumnChoice[];
}

export interface GridSort {
  /** The channel id whose values order the rows. */
  channelId: string;
  desc: boolean;
}

const MAX_FILTERS = 8;

/** "µM"; nothing for a unitless or unknown ("-") unit. */
const unitText = (unit: string) => (unit && unit !== "-" ? unit : "");

export function measurementFilterText(f: MeasurementFilter, label: string): string {
  const unit = unitText(f.unit);
  const range = [
    f.minimum != null ? `≥ ${f.minimum}` : "",
    f.maximum != null ? `≤ ${f.maximum}` : "",
  ]
    .filter(Boolean)
    .join(" ");
  return [
    `${label}${range ? ` ${range}${unit ? ` ${unit}` : ""}` : ""}`,
    f.qc !== "any" ? `QC ${QC_LABEL[f.qc].toLowerCase()}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

// ── Search ────────────────────────────────────────────────────────────────────

function SearchBox({ value, onSearch }: { value: string; onSearch: (search: string) => void }) {
  // What is typed, until Search; an applied search changed elsewhere (a chip) replaces it.
  const [draft, setDraft] = useState({ source: value, text: value });
  if (draft.source !== value) setDraft({ source: value, text: value });
  return (
    <form
      className="relative min-w-48 max-w-md flex-1"
      onSubmit={(e) => {
        e.preventDefault();
        onSearch(draft.text.trim());
      }}
    >
      <Search
        className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
      <Input
        className="h-8 pr-20 pl-8"
        aria-label="Search compound ID, name or alias"
        placeholder="Compound ID, name or alias"
        maxLength={200}
        value={draft.text}
        onChange={(e) => setDraft({ ...draft, text: e.target.value })}
      />
      <Button type="submit" variant="ghost" size="xs" className="absolute top-1 right-1">
        Search
      </Button>
    </form>
  );
}

// ── Filters ───────────────────────────────────────────────────────────────────

type Draft = Omit<MeasurementFilter, "minimum" | "maximum"> & { minimum: string; maximum: string };

const toDraft = (f: MeasurementFilter): Draft => ({
  ...f,
  minimum: f.minimum?.toString() ?? "",
  maximum: f.maximum?.toString() ?? "",
});

/** The drafts as filters, or what is wrong with them. */
export function parseFilterDrafts(
  drafts: Draft[],
  readouts: ReadoutOption[],
): MeasurementFilter[] | string {
  const out: MeasurementFilter[] = [];
  for (const d of drafts) {
    if (!readouts.some((r) => r.id === d.channelId)) return "Choose a readout for each condition.";
    const bound = (text: string) => (text.trim() === "" ? null : Number(text));
    const minimum = bound(d.minimum);
    const maximum = bound(d.maximum);
    if (
      (minimum != null && !Number.isFinite(minimum)) ||
      (maximum != null && !Number.isFinite(maximum))
    ) {
      return "Minimum and maximum must be numbers.";
    }
    if (minimum != null && maximum != null && minimum > maximum) {
      return "Minimum must not exceed maximum.";
    }
    if (minimum == null && maximum == null && d.qc === "any") {
      return "Set a minimum, a maximum or a QC state for each condition.";
    }
    out.push({ ...d, minimum, maximum });
  }
  return out;
}

function FiltersPopover({
  filters,
  readouts,
  onApply,
}: {
  filters: MeasurementFilter[];
  readouts: ReadoutOption[];
  onApply: (filters: MeasurementFilter[]) => void;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [error, setError] = useState<string | null>(null);
  const update = (index: number, patch: Partial<Draft>) => {
    setDrafts(drafts.map((d, i) => (i === index ? { ...d, ...patch } : d)));
    setError(null);
  };
  const apply = () => {
    const parsed = parseFilterDrafts(drafts, readouts);
    if (typeof parsed === "string") {
      setError(parsed);
      return;
    }
    onApply(parsed);
    setOpen(false);
  };
  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setDrafts(filters.map(toDraft));
          setError(null);
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm">
          <Filter />
          Filters
          {filters.length > 0 && (
            <span className="text-xs font-normal text-muted-foreground tabular-nums">
              ({filters.length})
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="flex max-h-(--radix-popover-content-available-height) w-[34rem] max-w-[calc(100vw-2rem)] flex-col p-0"
        aria-labelledby={`${id}-title`}
      >
        <div className="space-y-1 border-b p-3">
          <h3 id={`${id}-title`} className="text-sm font-semibold">
            Filter compounds
          </h3>
          <p className="text-xs text-muted-foreground">
            Every condition must hold. Hit criteria and stage outcomes are unchanged.
          </p>
        </div>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
          {drafts.length === 0 && (
            <p className="text-sm text-muted-foreground">No conditions yet.</p>
          )}
          {drafts.map((d, i) => {
            const unit = unitText(readouts.find((r) => r.id === d.channelId)?.unit ?? d.unit);
            return (
              // Conditions have no id and only append or drop.
              // biome-ignore lint/suspicious/noArrayIndexKey: see above
              <fieldset key={i} className="min-w-0 space-y-2 rounded-md border p-3">
                <legend className="px-1 text-xs font-medium">Condition {i + 1}</legend>
                <div className="flex items-center gap-2">
                  <Select
                    value={d.channelId}
                    onValueChange={(channelId) =>
                      update(i, {
                        channelId,
                        minimum: "",
                        maximum: "",
                        unit: readouts.find((r) => r.id === channelId)?.unit ?? "",
                      })
                    }
                  >
                    <SelectTrigger aria-label={`Readout ${i + 1}`} className="min-w-0 flex-1">
                      <SelectValue placeholder="Choose a readout" />
                    </SelectTrigger>
                    <SelectContent>
                      {readouts.map((r) => (
                        <SelectItem key={r.id} value={r.id}>
                          {r.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDrafts(drafts.filter((_, n) => n !== i))}
                  >
                    Remove
                  </Button>
                </div>
                <div className="grid grid-cols-[1fr_1fr_auto] items-end gap-2">
                  <Label className="flex flex-col items-start gap-1 text-xs font-normal">
                    Minimum
                    <Input
                      aria-label={`Minimum ${i + 1}`}
                      inputMode="decimal"
                      value={d.minimum}
                      onChange={(e) => update(i, { minimum: e.target.value })}
                    />
                  </Label>
                  <Label className="flex flex-col items-start gap-1 text-xs font-normal">
                    Maximum
                    <Input
                      aria-label={`Maximum ${i + 1}`}
                      inputMode="decimal"
                      value={d.maximum}
                      onChange={(e) => update(i, { maximum: e.target.value })}
                    />
                  </Label>
                  <span className="pb-2 text-xs text-muted-foreground">{unit || "no unit"}</span>
                </div>
                <Select
                  value={d.qc}
                  onValueChange={(qc: MeasurementFilter["qc"]) => update(i, { qc })}
                >
                  <SelectTrigger aria-label={`QC ${i + 1}`} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Any QC</SelectItem>
                    <SelectItem value="verified">QC verified</SelectItem>
                    <SelectItem value="failed">QC failed</SelectItem>
                    <SelectItem value="not_tested">QC not tested</SelectItem>
                  </SelectContent>
                </Select>
              </fieldset>
            );
          })}
          <Button
            variant="outline"
            size="sm"
            disabled={drafts.length >= MAX_FILTERS || readouts.length === 0}
            onClick={() => {
              const first = readouts[0];
              if (!first) return;
              setDrafts([
                ...drafts,
                { channelId: first.id, minimum: "", maximum: "", unit: first.unit, qc: "any" },
              ]);
            }}
          >
            <Plus />
            Add condition
          </Button>
          <p className="text-xs text-muted-foreground">
            Bounds are inclusive and in the unit shown. A range holds exact values only: never a
            limit (&lt; or &gt;), ND or an excluded value. QC not tested is a value nobody has
            checked yet.
          </p>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t p-3">
          <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={apply}>
            Apply filters
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

// ── Sort ──────────────────────────────────────────────────────────────────────

function SortPopover({
  sort,
  readouts,
  onApply,
}: {
  sort: GridSort | null;
  readouts: ReadoutOption[];
  onApply: (sort: GridSort | null) => void;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [field, setField] = useState("default");
  const [direction, setDirection] = useState("asc");
  const active = sort ? readouts.find((r) => r.id === sort.channelId) : undefined;
  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        if (next) {
          setField(active ? active.id : "default");
          setDirection(sort?.desc ? "desc" : "asc");
        }
        setOpen(next);
      }}
    >
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          aria-label={
            active && sort
              ? `Sort: ${active.label}, ${sort.desc ? "high to low" : "low to high"}`
              : "Sort"
          }
        >
          <ArrowDownUp />
          Sort
          {active && <span className="text-xs font-normal text-muted-foreground">(1)</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 space-y-3" aria-labelledby={`${id}-title`}>
        <h3 id={`${id}-title`} className="text-sm font-semibold">
          Sort compounds
        </h3>
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-field`}>Sort by</Label>
          <Select value={field} onValueChange={setField}>
            <SelectTrigger id={`${id}-field`} className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="default">Default order</SelectItem>
              {readouts.map((r) => (
                <SelectItem key={r.id} value={r.id}>
                  {r.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-direction`}>Direction</Label>
          <Select value={direction} onValueChange={setDirection} disabled={field === "default"}>
            <SelectTrigger id={`${id}-direction`} className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="asc">Low to high</SelectItem>
              <SelectItem value="desc">High to low</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <p className="text-xs text-muted-foreground">
          ND and blank values go last either way. A column's header sorts too.
        </p>
        <div className="flex justify-end gap-2 border-t pt-3">
          <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={() => {
              onApply(
                field === "default" ? null : { channelId: field, desc: direction === "desc" },
              );
              setOpen(false);
            }}
          >
            Apply sort
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

// ── Columns ───────────────────────────────────────────────────────────────────

function ColumnsPopover({
  groups,
  hidden,
  onChange,
}: {
  groups: ColumnGroup[];
  hidden: ReadonlySet<string>;
  onChange: (ids: string[], visible: boolean) => void;
}) {
  const id = useId();
  const all = groups.flatMap((g) => g.columns);
  const hiddenCount = all.filter((c) => hidden.has(c.id)).length;
  const empty = all.filter((c) => c.empty).map((c) => c.id);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          aria-label={hiddenCount > 0 ? `Columns, ${hiddenCount} hidden` : "Columns"}
        >
          <Columns3 />
          Columns
          {hiddenCount > 0 && (
            <span className="text-xs font-normal text-muted-foreground tabular-nums">
              {hiddenCount} hidden
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="flex max-h-(--radix-popover-content-available-height) w-80 flex-col p-0"
        aria-labelledby={`${id}-title`}
      >
        <div className="space-y-1 border-b p-3">
          <h3 id={`${id}-title`} className="text-sm font-semibold">
            Table columns
          </h3>
          <p className="text-xs text-muted-foreground">
            For you, on this campaign, in this browser. Columns with no value yet start hidden.
          </p>
        </div>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
          {groups.map((g) => (
            <div key={g.title} className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">{g.title}</p>
              {g.columns.map((c) => (
                <Label key={c.id} className="flex items-center gap-2 text-sm font-normal">
                  <Checkbox
                    checked={!hidden.has(c.id)}
                    onCheckedChange={(v) => onChange([c.id], v === true)}
                  />
                  <span className="min-w-0 flex-1 truncate">{c.label}</span>
                  {c.empty && <span className="text-xs text-muted-foreground">no values</span>}
                </Label>
              ))}
            </div>
          ))}
        </div>
        <div className="flex justify-between gap-2 border-t p-3">
          <Button
            variant="ghost"
            size="sm"
            disabled={empty.length === 0}
            onClick={() => onChange(empty, false)}
          >
            Hide empty
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={hiddenCount === 0}
            onClick={() =>
              onChange(
                all.map((c) => c.id),
                true,
              )
            }
          >
            Show all
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

// ── Toolbar ───────────────────────────────────────────────────────────────────

export interface ResultsToolbarProps {
  filters: CampaignFilters;
  onFiltersChange: (next: CampaignFilters) => void;
  /** Readouts in view, for new conditions. */
  readouts: ReadoutOption[];
  /** Every readout's label, so a condition on one out of view still reads. */
  labelOf: (channelId: string) => string;
  /** Readouts with a column shown, for sorting. */
  sortable: ReadoutOption[];
  sort: GridSort | null;
  onSortChange: (sort: GridSort | null) => void;
  columns: ColumnGroup[];
  hidden: ReadonlySet<string>;
  onColumnsChange: (ids: string[], visible: boolean) => void;
  maximized: boolean;
  onMaximizedChange: (maximized: boolean) => void;
}

export function ResultsToolbar({
  filters,
  onFiltersChange,
  readouts,
  labelOf,
  sortable,
  sort,
  onSortChange,
  columns,
  hidden,
  onColumnsChange,
  maximized,
  onMaximizedChange,
}: ResultsToolbarProps) {
  const applied = filters.search !== "" || filters.measurements.length > 0;
  return (
    <div className="space-y-2 border-b px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <SearchBox
          value={filters.search}
          onSearch={(search) => onFiltersChange({ ...filters, search })}
        />
        <FiltersPopover
          filters={filters.measurements}
          readouts={readouts}
          onApply={(measurements) => onFiltersChange({ ...filters, measurements })}
        />
        <SortPopover sort={sort} readouts={sortable} onApply={onSortChange} />
        <ColumnsPopover groups={columns} hidden={hidden} onChange={onColumnsChange} />
        <Button
          variant="outline"
          size="sm"
          className="ml-auto"
          data-maximize
          aria-pressed={maximized}
          onClick={() => onMaximizedChange(!maximized)}
        >
          {maximized ? <Minimize2 /> : <Maximize2 />}
          {maximized ? "Restore" : "Maximize"}
        </Button>
      </div>
      {applied && (
        <div className="flex flex-wrap items-center gap-2" aria-label="Applied search and filters">
          {filters.search && (
            <Button
              size="xs"
              variant="outline"
              className="max-w-full"
              aria-label="Remove search"
              onClick={() => onFiltersChange({ ...filters, search: "" })}
            >
              <span className="truncate">Search: {filters.search}</span>
              <X />
            </Button>
          )}
          {filters.measurements.map((f, i) => (
            <Button
              // biome-ignore lint/suspicious/noArrayIndexKey: conditions have no id
              key={i}
              size="xs"
              variant="outline"
              className="max-w-full"
              aria-label={`Remove condition ${i + 1}`}
              onClick={() =>
                onFiltersChange({
                  ...filters,
                  measurements: filters.measurements.filter((_, n) => n !== i),
                })
              }
            >
              <span className="truncate">{measurementFilterText(f, labelOf(f.channelId))}</span>
              <X />
            </Button>
          ))}
          <Button
            size="xs"
            variant="ghost"
            onClick={() => onFiltersChange({ ...filters, search: "", measurements: [] })}
          >
            Clear search and filters
          </Button>
        </div>
      )}
    </div>
  );
}
