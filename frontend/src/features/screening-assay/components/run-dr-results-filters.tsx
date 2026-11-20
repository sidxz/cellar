"use client";

import { Button } from "@/shared/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
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
import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";
import { interceptLabel } from "../lib/intercept-label";
import { CURVE_CLASS_LABELS, type InterceptSpec } from "../types";
import type {
  PotencyComparison,
  RunCurveClassFilter,
  RunPotencyFilter,
} from "./run-dr-results-filtering";
import { displayDoseUnit, doseUnitScale } from "./run-dr-results-view";

const COMPARISONS: Record<PotencyComparison, { label: string; symbol: string }> = {
  lt: { label: "Below (<)", symbol: "<" },
  lte: { label: "At most (≤)", symbol: "≤" },
  gt: { label: "Above (>)", symbol: ">" },
  gte: { label: "At least (≥)", symbol: "≥" },
};

export function RunCurveClassFilterMenu({
  selected,
  onChange,
  hasUnclassified,
}: {
  selected: RunCurveClassFilter[];
  onChange: (classes: RunCurveClassFilter[]) => void;
  hasUnclassified: boolean;
}) {
  const options: Array<[RunCurveClassFilter, string]> = Object.entries(CURVE_CLASS_LABELS) as Array<
    [RunCurveClassFilter, string]
  >;
  if (hasUnclassified || selected.includes("unclassified"))
    options.push(["unclassified", "Unclassified"]);
  const single = options.find(([value]) => value === selected[0])?.[1];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant={selected.length ? "secondary" : "outline"}
          size="sm"
          aria-label="Filter by curve class"
        >
          {selected.length === 1
            ? `Class: ${single}`
            : `Curve class${selected.length ? ` (${selected.length})` : ""}`}
          <ChevronDown className="size-3.5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel>Show curve classes</DropdownMenuLabel>
        <DropdownMenuCheckboxItem
          checked={selected.length === 0}
          onCheckedChange={() => onChange([])}
          onSelect={(event) => event.preventDefault()}
        >
          All curve classes
        </DropdownMenuCheckboxItem>
        <DropdownMenuSeparator />
        {options.map(([value, label]) => (
          <DropdownMenuCheckboxItem
            key={value}
            checked={selected.includes(value)}
            onSelect={(event) => event.preventDefault()}
            onCheckedChange={(checked) =>
              onChange(checked ? [...selected, value] : selected.filter((item) => item !== value))
            }
          >
            {label}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function RunPotencyFilterControl({
  intercepts,
  unit,
  value,
  onChange,
}: {
  intercepts: InterceptSpec[];
  unit: string | null;
  value: RunPotencyFilter | null;
  onChange: (filter: RunPotencyFilter | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [endpoint, setEndpoint] = useState("0");
  const [operator, setOperator] = useState<PotencyComparison>("lte");
  const [threshold, setThreshold] = useState("");
  const [error, setError] = useState<string | null>(null);
  const id = useId();
  const shownUnit = unit ?? value?.unit ?? "";
  const summary = value
    ? `${value.spec ? interceptLabel(value.spec) : "Fitted value"} ${COMPARISONS[value.operator].symbol} ${Number((value.threshold * doseUnitScale(value.unit, shownUnit)).toPrecision(4))} ${displayDoseUnit(shownUnit)}`
    : "Potency";

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        if (next) {
          const index = value?.spec
            ? intercepts.findIndex(
                (spec) => spec.kind === value.spec?.kind && spec.level === value.spec.level,
              )
            : 0;
          setEndpoint(String(Math.max(0, index)));
          setOperator(value?.operator ?? "lte");
          setThreshold(
            value
              ? String(
                  Number((value.threshold * doseUnitScale(value.unit, shownUnit)).toPrecision(12)),
                )
              : "",
          );
          setError(null);
        }
        setOpen(next);
      }}
    >
      <PopoverTrigger asChild>
        <Button
          variant={value ? "secondary" : "outline"}
          size="sm"
          disabled={!unit}
          aria-label="Filter by potency"
          title={!unit ? "Potency units differ across these results" : undefined}
        >
          {summary}
          <ChevronDown className="size-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 max-w-[calc(100vw-2rem)]">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            const number = Number(threshold);
            if (!unit || !threshold.trim() || !Number.isFinite(number) || number <= 0) {
              setError("Enter a concentration greater than zero.");
              return;
            }
            const index = Number(endpoint);
            onChange({
              spec: intercepts[index] ?? null,
              primary: index === 0,
              operator,
              threshold: number,
              unit,
            });
            setOpen(false);
          }}
        >
          <div>
            <p className="text-sm font-medium">Filter by potency</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Only changes the rows shown in this table.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor={`${id}-endpoint`}>Endpoint</Label>
            <Select value={endpoint} onValueChange={setEndpoint}>
              <SelectTrigger id={`${id}-endpoint`} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {intercepts.length ? (
                  intercepts.map((spec, index) => (
                    <SelectItem key={`${spec.kind}:${spec.level}`} value={String(index)}>
                      {interceptLabel(spec)}
                    </SelectItem>
                  ))
                ) : (
                  <SelectItem value="0">Fitted value</SelectItem>
                )}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor={`${id}-comparison`}>Comparison</Label>
            <Select
              value={operator}
              onValueChange={(next) => {
                if (Object.hasOwn(COMPARISONS, next)) setOperator(next as PotencyComparison);
              }}
            >
              <SelectTrigger id={`${id}-comparison`} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(COMPARISONS).map(([key, option]) => (
                  <SelectItem key={key} value={key}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor={`${id}-threshold`}>Concentration ({displayDoseUnit(shownUnit)})</Label>
            <Input
              id={`${id}-threshold`}
              type="number"
              min="0"
              step="any"
              required
              value={threshold}
              onChange={(event) => setThreshold(event.target.value)}
              aria-invalid={!!error}
            />
            {error && (
              <p role="alert" className="text-xs text-destructive">
                {error}
              </p>
            )}
          </div>
          <div className="flex items-center justify-between gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={!value}
              onClick={() => {
                onChange(null);
                setOpen(false);
              }}
            >
              Clear potency
            </Button>
            <Button type="submit" size="sm">
              Apply filter
            </Button>
          </div>
        </form>
      </PopoverContent>
    </Popover>
  );
}
