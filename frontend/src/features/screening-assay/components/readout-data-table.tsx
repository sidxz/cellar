"use client";

import { Skeleton } from "@/shared/components/ui/skeleton";
import { Badge } from "@/shared/components/ui/badge";
import { cn } from "@/shared/lib/utils";
import { useMolecules } from "@/features/chemical-registration/hooks/use-molecules";
import { useProtocol } from "../hooks/use-protocols";
import { useReadoutDataByRun } from "../hooks/use-readout-data";

interface ReadoutDataTableProps {
  runId: string;
  protocolId: string;
  className?: string;
}

export function ReadoutDataTable({
  runId,
  protocolId,
  className,
}: ReadoutDataTableProps) {
  const { data, isLoading } = useReadoutDataByRun(runId);
  const { data: molecules } = useMolecules();
  const { data: protocol } = useProtocol(protocolId);

  // Build lookup maps
  const molMap = new Map<string, string>();
  for (const mol of molecules ?? []) {
    molMap.set(mol.id, `${mol.registration_number} — ${mol.name}`);
  }

  const rdDefMap = new Map<string, string>();
  for (const rd of protocol?.readout_definitions ?? []) {
    rdDefMap.set(rd.id, rd.unit ? `${rd.name} (${rd.unit})` : rd.name);
  }

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
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">
              Measurement
            </th>
            <th className="px-3 py-2 text-right font-medium text-muted-foreground">
              Value
            </th>
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">
              Qualifier
            </th>
            <th className="px-3 py-2 text-center font-medium text-muted-foreground">
              Outlier
            </th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr
              key={row.id}
              className="border-b last:border-b-0 hover:bg-muted/50"
            >
              <td className="px-3 py-2 text-xs">
                {molMap.get(row.molecule_id) ?? row.molecule_id.slice(0, 8)}
              </td>
              <td className="px-3 py-2 font-medium">
                {rdDefMap.get(row.readout_definition_id) ?? "—"}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {row.value_numeric !== null && row.value_numeric !== undefined
                  ? row.value_numeric.toFixed(3)
                  : row.value_text ?? "—"}
              </td>
              <td className="px-3 py-2 text-muted-foreground">
                {row.value_qualifier ?? "="}
              </td>
              <td className="px-3 py-2 text-center">
                {row.is_outlier ? (
                  <Badge variant="destructive" className="text-xs">
                    Outlier
                  </Badge>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
