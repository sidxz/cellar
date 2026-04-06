"use client";

import { useMemo, useState } from "react";
import type { ColDef } from "ag-grid-community";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useConditionGroups } from "../hooks/use-condition-groups";
import type { ConditionDefinition, ConditionGroupResponse } from "../types";

interface ConditionGroupTableProps {
  protocolId: string;
  conditionDefinitions: ConditionDefinition[];
  className?: string;
}

export function ConditionGroupTable({
  protocolId,
  conditionDefinitions,
  className,
}: ConditionGroupTableProps) {
  const [selectedCondition, setSelectedCondition] = useState<string>(
    conditionDefinitions[0]?.name ?? ""
  );

  const { data, isLoading } = useConditionGroups(
    protocolId,
    selectedCondition || undefined
  );

  // Build columns dynamically: condition_value + run_count + one per readout
  const columnDefs = useMemo<ColDef<ConditionGroupResponse>[]>(() => {
    const cols: ColDef<ConditionGroupResponse>[] = [
      {
        headerName: selectedCondition || "Condition",
        field: "condition_value",
        flex: 1,
        minWidth: 140,
      },
      {
        headerName: "Runs",
        field: "run_count",
        width: 80,
        cellClass: "text-right tabular-nums",
        headerClass: "ag-right-aligned-header",
      },
    ];

    // Derive readout columns from the first group's aggregated readouts
    const readouts = data?.groups?.[0]?.aggregated_readouts ?? [];
    for (const rd of readouts) {
      cols.push({
        headerName: rd.unit
          ? `${rd.name} (${rd.aggregation}, ${rd.unit})`
          : `${rd.name} (${rd.aggregation})`,
        colId: rd.readout_definition_id,
        width: 160,
        cellClass: "text-right tabular-nums",
        headerClass: "ag-right-aligned-header",
        valueGetter: (p) => {
          const match = p.data?.aggregated_readouts.find(
            (r) => r.readout_definition_id === rd.readout_definition_id
          );
          return match?.value ?? null;
        },
        valueFormatter: (p) =>
          p.value !== null && p.value !== undefined
            ? Number(p.value).toFixed(3)
            : "\u2014",
      });
    }

    return cols;
  }, [selectedCondition, data]);

  if (conditionDefinitions.length === 0) {
    return null;
  }

  return (
    <div className={className}>
      <div className="mb-4 flex items-center gap-3">
        <Label className="shrink-0 text-sm">Group by condition:</Label>
        <Select value={selectedCondition} onValueChange={setSelectedCondition}>
          <SelectTrigger className="w-[220px]">
            <SelectValue placeholder="Select condition..." />
          </SelectTrigger>
          <SelectContent>
            {conditionDefinitions.map((cd) => (
              <SelectItem key={cd.id} value={cd.name}>
                {cd.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <DataGrid<ConditionGroupResponse>
        rowData={data?.groups ?? []}
        columnDefs={columnDefs}
        loading={isLoading}
        height="300px"
        suppressFilters
        getRowId={(params) => params.data.condition_value}
        emptyState={
          <p className="py-8 text-center text-sm text-muted-foreground">
            No condition grouping data available.
          </p>
        }
      />
    </div>
  );
}
