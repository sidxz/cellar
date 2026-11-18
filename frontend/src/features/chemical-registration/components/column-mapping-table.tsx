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
import { Fragment } from "react";
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
}

/** The rows of a mapping: where each goes, its Source, and the ";" choice. */
export function ColumnMappingTable({
  rows,
  mapping,
  onChange,
  rowHeading = "Column in file",
  hideSmiles,
  groupTitles,
}: Props) {
  // Single-valued targets already used, and by which row.
  const takenBy = new Map<ColumnTarget, string>();
  const labelOf = new Map(rows.map((r) => [r.key, r.label]));
  for (const c of mapping.columns) {
    if (!isMulti(c.target)) takenBy.set(c.target, labelOf.get(c.header) ?? c.header);
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
          <th className="px-3 py-2 text-left font-medium">Goes to</th>
          <th className="px-3 py-2 text-left font-medium">Source</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const c = mapping.columns.find((m) => m.header === r.key);
          if (!c) return null;
          const samples = r.samples ?? [];
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
                  <td className="px-3 py-2 text-xs text-muted-foreground max-w-[280px] truncate">
                    {r.samples === undefined
                      ? ""
                      : samples.length > 0
                        ? samples.join(", ")
                        : "(empty in this file)"}
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
                              const usedElsewhere = !!owner && owner !== r.label;
                              return (
                                <SelectItem key={t} value={t} disabled={usedElsewhere}>
                                  {TARGET_LABELS[t]}
                                  {usedElsewhere ? ` (used by ${owner})` : ""}
                                </SelectItem>
                              );
                            })}
                        </SelectGroup>
                      ))}
                      <SelectSeparator />
                      <SelectItem value="ignore">{TARGET_LABELS.ignore}</SelectItem>
                    </SelectContent>
                  </Select>
                </td>
                <td className="px-3 py-2">
                  {isLabelled(c.target) && (
                    <Input
                      className="h-8 w-56"
                      value={c.source ?? ""}
                      onChange={(e) => update(r.key, { source: e.target.value })}
                      aria-label={`Source for ${r.label}`}
                    />
                  )}
                  {isSplittable(c.target) && (
                    <label className="mt-1.5 flex items-center gap-2 text-xs text-muted-foreground">
                      <Checkbox
                        checked={c.separator === ";"}
                        onCheckedChange={(on) => update(r.key, { separator: on ? ";" : undefined })}
                        aria-label={`Several values, separated by ; (${r.label})`}
                      />
                      Several values, separated by ;
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
