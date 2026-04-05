"use client";

import { useMemo } from "react";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { cn } from "@/shared/lib/utils";
import { useMolecules } from "@/features/chemical-registration/hooks/use-molecules";
import { useProtocol } from "../hooks/use-protocols";
import { useReadoutDataByRun } from "../hooks/use-readout-data";
import type { ReadoutData } from "../types";

interface ReadoutDataTableProps {
  runId: string;
  protocolId: string;
  className?: string;
}

/** Format a value with qualifier prefix: "85.2", "<12.7", ">1000" */
function formatValue(row: ReadoutData): string {
  if (row.value_numeric === null || row.value_numeric === undefined) {
    return row.value_text ?? "—";
  }
  const prefix =
    row.value_qualifier && row.value_qualifier !== "=" ? row.value_qualifier : "";
  return `${prefix}${row.value_numeric.toFixed(3)}`;
}

/**
 * Pivoted readout data table.
 *
 * Readout definitions become column headers. One row per compound-batch pair.
 * Outlier values are highlighted. Qualifiers are shown as value prefixes.
 */
export function ReadoutDataTable({
  runId,
  protocolId,
  className,
}: ReadoutDataTableProps) {
  const { data, isLoading } = useReadoutDataByRun(runId);
  const { data: molecules } = useMolecules();
  const { data: protocol } = useProtocol(protocolId);

  const readoutDefs = protocol?.readout_definitions ?? [];

  // Build molecule lookup
  const molMap = useMemo(() => {
    const m = new Map<string, { reg: string; name: string }>();
    for (const mol of molecules ?? []) {
      m.set(mol.id, { reg: mol.registration_number, name: mol.name });
    }
    return m;
  }, [molecules]);

  // Pivot: group readout data by (molecule_id, batch_id), then index by readout_definition_id
  const pivoted = useMemo(() => {
    if (!data) return [];

    const groups = new Map<
      string,
      {
        moleculeId: string;
        batchId: string;
        values: Map<string, ReadoutData>;
      }
    >();

    for (const row of data) {
      const key = `${row.molecule_id}::${row.batch_id}`;
      let group = groups.get(key);
      if (!group) {
        group = {
          moleculeId: row.molecule_id,
          batchId: row.batch_id,
          values: new Map(),
        };
        groups.set(key, group);
      }
      group.values.set(row.readout_definition_id, row);
    }

    return Array.from(groups.values());
  }, [data]);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No readout data recorded for this run.
      </p>
    );
  }

  return (
    <div
      className={cn(
        "max-h-[500px] overflow-auto rounded-md border",
        className
      )}
    >
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-background">
          <tr className="border-b">
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">
              Compound
            </th>
            {readoutDefs.map((rd) => (
              <th
                key={rd.id}
                className="px-3 py-2 text-right font-medium text-muted-foreground"
              >
                <div>{rd.name}</div>
                {rd.unit && (
                  <div className="text-xs font-normal">({rd.unit})</div>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {pivoted.map((group) => {
            const mol = molMap.get(group.moleculeId);
            const label = mol
              ? `${mol.reg} — ${mol.name}`
              : group.moleculeId.slice(0, 8);

            return (
              <tr
                key={`${group.moleculeId}::${group.batchId}`}
                className="border-b last:border-b-0 hover:bg-muted/50"
              >
                <td className="px-3 py-2 text-xs whitespace-nowrap">
                  {label}
                </td>
                {readoutDefs.map((rd) => {
                  const row = group.values.get(rd.id);
                  if (!row) {
                    return (
                      <td
                        key={rd.id}
                        className="px-3 py-2 text-right text-muted-foreground"
                      >
                        —
                      </td>
                    );
                  }
                  return (
                    <td
                      key={rd.id}
                      className={cn(
                        "px-3 py-2 text-right tabular-nums",
                        row.is_outlier &&
                          "text-destructive line-through decoration-destructive/50"
                      )}
                      title={row.is_outlier ? "Flagged as outlier" : undefined}
                    >
                      {formatValue(row)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
