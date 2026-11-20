"use client";

import { StructureRenderer, StructureThumbnail } from "@/shared/components/chemistry";
import { EntityLink } from "@/shared/components/entity-link";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/components/ui/tooltip";
import { Check, Copy, Maximize2, Minimize2 } from "lucide-react";
import { type RefObject, useEffect, useRef, useState } from "react";
import type { CurveFrame } from "../lib/curve-frame";
import { CURVE_CLASS_LABELS } from "../types";
import { DoseResponseSparkline } from "./dose-response-sparkline";
import type { CompoundCurveRow } from "./run-dr-results-transforms";

export function RunResultsMaximizeHeader({
  expanded,
  onToggle,
  buttonRef,
}: {
  expanded: boolean;
  onToggle: () => void;
  buttonRef?: RefObject<HTMLButtonElement | null>;
}) {
  const label = expanded ? "Restore table" : "Maximize table";
  return (
    <div className="flex h-full w-full items-center justify-center">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            ref={buttonRef}
            variant="ghost"
            size="icon"
            className="size-8"
            aria-label={label}
            aria-pressed={expanded}
            onClick={onToggle}
          >
            {expanded ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="left">{label}</TooltipContent>
      </Tooltip>
    </div>
  );
}

function Highlight({ text, query }: { text: string; query: string }) {
  const match = query.trim();
  const index = match ? text.toLocaleLowerCase().indexOf(match.toLocaleLowerCase()) : -1;
  if (index < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, index)}
      <mark className="rounded-sm bg-primary/15 text-foreground">
        {text.slice(index, index + match.length)}
      </mark>
      {text.slice(index + match.length)}
    </>
  );
}

export function RunCompoundCell({ data, query = "" }: { data: CompoundCurveRow; query?: string }) {
  const [copied, setCopied] = useState(false);
  const aliases = [...new Set([data.molecule_name, ...(data.synonyms ?? [])])].filter(
    (name): name is string => !!name && name !== data.registration_number,
  );
  // Put a recognizable name ahead of catalog codes, and always surface a matching alias.
  const code = /^[a-z][a-z\d]*[-_]\d[\w-]*$/i;
  const search = query.trim().toLocaleLowerCase();
  const ordered = aliases.toSorted((a, b) => {
    const aMatches = !!search && a.toLocaleLowerCase().includes(search);
    const bMatches = !!search && b.toLocaleLowerCase().includes(search);
    return Number(bMatches) - Number(aMatches) || Number(code.test(a)) - Number(code.test(b));
  });
  const visible = ordered.slice(0, 2);

  return (
    <div className="flex min-w-0 flex-col items-start gap-1 whitespace-normal py-2 leading-snug">
      <EntityLink
        type="compound"
        id={data.molecule_id}
        label={data.registration_number}
        className="break-words font-sans font-semibold"
      />
      {visible.map((alias) => (
        <span key={alias} className="max-w-full break-words text-xs text-foreground/80">
          <Highlight text={alias} query={query} />
        </span>
      ))}
      {ordered.length > 2 && (
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              className="rounded-sm text-xs font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring"
              aria-label={`Show all aliases for ${data.registration_number}`}
            >
              +{ordered.length - 2} {ordered.length === 3 ? "alias" : "aliases"}
            </button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-80 max-w-[calc(100vw-2rem)] space-y-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium">Compound identifiers</p>
              <Button
                size="sm"
                variant="ghost"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(
                      [data.registration_number, ...aliases, data.batch_number]
                        .filter(Boolean)
                        .join("\n"),
                    );
                    setCopied(true);
                  } catch {
                    setCopied(false);
                  }
                }}
              >
                {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                {copied ? "Copied" : "Copy all"}
              </Button>
            </div>
            <p className="break-words text-sm font-medium">{data.registration_number}</p>
            <ul className="max-h-60 space-y-2 overflow-y-auto text-sm">
              {aliases.map((alias) => (
                <li key={alias} className="break-words select-text">
                  <Highlight text={alias} query={query} />
                </li>
              ))}
            </ul>
            {data.batch_number && (
              <p className="border-t pt-2 text-xs text-muted-foreground">
                Batch: {data.batch_number}
              </p>
            )}
          </PopoverContent>
        </Popover>
      )}
      {data.batch_number && (
        <span className="mt-1 max-w-full break-words text-xs text-muted-foreground">
          Batch: <Highlight text={data.batch_number} query={query} />
        </span>
      )}
    </div>
  );
}

export function RunStructureCell({
  data,
}: { data: Pick<CompoundCurveRow, "smiles" | "registration_number"> }) {
  const previewRef = useRef<HTMLDivElement>(null);
  const [canvas, setCanvas] = useState<{ width: number; height: number } | null>(null);

  useEffect(() => {
    const element = previewRef.current;
    if (!data.smiles || !element) return;
    const updateSize = (width: number, height: number) => {
      const next = { width: Math.floor(width), height: Math.floor(height) };
      if (next.width <= 0 || next.height <= 0) return;
      setCanvas((previous) =>
        previous?.width === next.width && previous.height === next.height ? previous : next,
      );
    };
    const bounds = element.getBoundingClientRect();
    updateSize(bounds.width, bounds.height);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) updateSize(entry.contentRect.width, entry.contentRect.height);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [data.smiles]);

  if (!data.smiles) return <span className="text-xs text-muted-foreground">No structure</span>;

  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          aria-label={`Enlarge structure for ${data.registration_number}`}
          className="group relative flex h-full w-full items-center justify-center rounded-md p-2 focus-visible:outline-2 focus-visible:outline-ring"
        >
          <div ref={previewRef} className="h-full w-full overflow-hidden">
            {canvas ? (
              <StructureThumbnail
                smiles={data.smiles}
                size={canvas.width}
                height={canvas.height}
                className="h-full w-full object-contain"
              />
            ) : (
              <div className="h-full w-full animate-pulse rounded bg-muted" />
            )}
          </div>
          <Maximize2 className="absolute right-2 top-2 size-3 text-muted-foreground/60 group-hover:text-foreground" />
        </button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{data.registration_number}</DialogTitle>
          <DialogDescription>Chemical structure</DialogDescription>
        </DialogHeader>
        <div className="flex min-w-0 items-center justify-center">
          <StructureRenderer
            smiles={data.smiles}
            width={520}
            height={360}
            className="h-auto max-w-full"
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function RunResponseCell({
  data,
  frame,
  compact = false,
  onView,
}: {
  data: CompoundCurveRow;
  frame?: CurveFrame;
  compact?: boolean;
  onView?: (moleculeId: string) => void;
}) {
  const plotRef = useRef<HTMLDivElement>(null);
  const [plotWidth, setPlotWidth] = useState(compact ? 240 : 300);

  useEffect(() => {
    const element = plotRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const width = Math.min(compact ? 240 : 300, Math.floor(entry.contentRect.width));
      if (width > 0) setPlotWidth(width);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [compact]);

  return (
    <button
      type="button"
      aria-label={`View dose-response details for ${data.registration_number}`}
      onClick={() => onView?.(data.molecule_id)}
      className="flex h-full w-full flex-col items-center justify-center gap-1 rounded-md py-2 text-left focus-visible:outline-2 focus-visible:outline-ring"
    >
      <div ref={plotRef} className="pointer-events-none flex w-full justify-center">
        <DoseResponseSparkline
          params={{
            hill_slope: data.hill_slope,
            top: data.top,
            bottom: data.bottom,
            fitted_value: data.fitted_value,
            r_squared: data.r_squared,
          }}
          dataPoints={data.data_points}
          curveClass={data.curve_class}
          interceptValues={data.intercept_values}
          width={plotWidth}
          height={Math.round((plotWidth * 2) / 3)}
          xRange={frame?.xRange}
          yRange={frame?.yRange}
        />
      </div>
      <span className="max-w-full whitespace-normal text-center text-xs font-normal leading-tight text-muted-foreground">
        {data.curve_class ? CURVE_CLASS_LABELS[data.curve_class] : "Unclassified"}
      </span>
    </button>
  );
}
