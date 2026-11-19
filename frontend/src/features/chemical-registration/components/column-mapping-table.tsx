"use client";

import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import type { ColumnMappingBody, ColumnTarget } from "@/shared/lib/api/model";
import { Fragment, useId } from "react";
import {
  TARGET_GROUPS,
  TARGET_LABELS,
  isLabelled,
  isMulti,
  isSplittable,
} from "../lib/column-targets";

export type MappingGroup = "Compound" | "Batch";

export interface MappingRow {
  /** The mapping column's `header` this row edits. */
  key: string;
  label: string;
  /** Limits the targets offered to this group's; absent = all. */
  group?: MappingGroup;
  /** A file column's values; no row with samples = no Sample values column. */
  samples?: string[];
}

interface Props {
  rows: MappingRow[];
  mapping: ColumnMappingBody;
  onChange: (mapping: ColumnMappingBody) => void;
  /** First column's heading. */
  rowHeading?: string;
  /** SDF files: the structure always comes from the record itself. */
  hideSmiles?: boolean;
  /** Section titles shown when a row's group changes. */
  groupTitles?: Record<MappingGroup, string>;
  /** The "not imported" choice, in the page's own words (a vault field is not a column). */
  ignoreLabel?: string;
}

/** The rows of a mapping: where each goes, its Source, and the ";" choice. */
export function ColumnMappingTable({
  rows,
  mapping,
  onChange,
  rowHeading = "Column in file",
  hideSmiles,
  groupTitles,
  ignoreLabel = TARGET_LABELS.ignore,
}: Props) {
  const tableId = useId();
  // Single-valued targets already used, and by which row (its key: two rows may share a label).
  const takenBy = new Map<ColumnTarget, { key: string; label: string }>();
  const labelOf = new Map(rows.map((r) => [r.key, r.label]));
  for (const c of mapping.columns) {
    if (!isMulti(c.target)) {
      takenBy.set(c.target, { key: c.header, label: labelOf.get(c.header) ?? c.header });
    }
  }

  const update = (key: string, patch: Partial<ColumnMappingBody["columns"][number]>) =>
    onChange({ columns: mapping.columns.map((c) => (c.header === key ? { ...c, ...patch } : c)) });

  const showSamples = rows.some((r) => r.samples !== undefined);
  let lastGroup: MappingGroup | undefined;
  return (
    <table className="w-full text-sm">
      <thead className="sticky top-0 bg-muted/80 backdrop-blur">
        <tr className="border-b text-xs">
          <th className="px-3 py-2 text-left font-medium">{rowHeading}</th>
          {showSamples && <th className="px-3 py-2 text-left font-medium">Sample values</th>}
          <th className="px-3 py-2 text-left font-medium">Destination field</th>
          <th className="px-3 py-2 text-left font-medium">Field options</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const c = mapping.columns.find((m) => m.header === r.key);
          if (!c) return null;
          const samples = r.samples ?? [];
          const sourceId = `${tableId}-${encodeURIComponent(r.key)}-source`;
          const splitId = `${tableId}-${encodeURIComponent(r.key)}-split`;
          const title = r.group && r.group !== lastGroup ? groupTitles?.[r.group] : undefined;
          lastGroup = r.group;
          const groups = TARGET_GROUPS.filter((g) => !r.group || g.label === r.group);
          return (
            <Fragment key={r.key}>
              {title && (
                <tr className="border-b bg-muted/40">
                  <th
                    colSpan={showSamples ? 4 : 3}
                    className="px-3 py-1.5 text-left text-xs font-semibold"
                  >
                    {title}
                  </th>
                </tr>
              )}
              <tr className="border-b last:border-b-0">
                <td className="px-3 py-2 font-medium">{r.label}</td>
                {showSamples && (
                  <td className="max-w-[280px] px-3 py-2 text-sm text-foreground/70">
                    {r.samples === undefined ? (
                      ""
                    ) : samples.length > 0 ? (
                      <div className="space-y-1">
                        {samples.map((sample, index) =>
                          sample.length > 64 ? (
                            <details key={sample} className="min-w-0">
                              <summary
                                className="cursor-pointer truncate"
                                title="Expand sample value"
                              >
                                <span className="mr-2 text-xs font-medium">Sample {index + 1}</span>
                                {sample}
                              </summary>
                              <p className="mt-1 whitespace-pre-wrap break-all rounded bg-muted/40 p-2 font-mono text-xs">
                                {sample}
                              </p>
                            </details>
                          ) : (
                            <div key={sample}>
                              <span className="mr-2 text-xs font-medium">Sample {index + 1}</span>
                              <span>{sample}</span>
                            </div>
                          ),
                        )}
                      </div>
                    ) : (
                      "No sample values"
                    )}
                  </td>
                )}
                <td className="px-3 py-2">
                  <Select
                    value={c.target}
                    onValueChange={(v) => {
                      const target = v as ColumnTarget;
                      update(r.key, {
                        target,
                        source: isLabelled(target) ? c.source?.trim() || r.label : null,
                        separator: undefined,
                      });
                    }}
                  >
                    <SelectTrigger className="h-8 w-56" aria-label={`Where ${r.label} goes`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {groups.map((g) => (
                        <SelectGroup key={g.label}>
                          <SelectLabel>{g.label}</SelectLabel>
                          {g.targets
                            .filter((t) => !(hideSmiles && t === "smiles"))
                            .map((t) => {
                              const owner = takenBy.get(t);
                              const usedElsewhere = !!owner && owner.key !== r.key;
                              return (
                                <SelectItem key={t} value={t} disabled={usedElsewhere}>
                                  {TARGET_LABELS[t]}
                                  {usedElsewhere ? ` (used by ${owner.label})` : ""}
                                </SelectItem>
                              );
                            })}
                        </SelectGroup>
                      ))}
                      <SelectSeparator />
                      <SelectItem value="ignore">{ignoreLabel}</SelectItem>
                    </SelectContent>
                  </Select>
                </td>
                <td className="px-3 py-2">
                  {isLabelled(c.target) && (
                    <label htmlFor={sourceId} className="grid gap-1 text-xs text-foreground/70">
                      {c.target === "compound_id" || c.target === "batch_id"
                        ? "Identifier source"
                        : "Custom field name"}
                      <Input
                        id={sourceId}
                        className="h-8 w-full min-w-40"
                        value={c.source ?? ""}
                        onChange={(e) => update(r.key, { source: e.target.value })}
                        aria-label={`Source for ${r.label}`}
                      />
                    </label>
                  )}
                  {isSplittable(c.target) && (
                    <label
                      htmlFor={splitId}
                      className="mt-2 flex items-center gap-2 text-sm text-foreground/70"
                    >
                      <Checkbox
                        id={splitId}
                        checked={c.separator === ";"}
                        onCheckedChange={(on) => update(r.key, { separator: on ? ";" : undefined })}
                        aria-label={`Split values on semicolons (${r.label})`}
                      />
                      Split values on semicolons (;)
                    </label>
                  )}
                </td>
              </tr>
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}
