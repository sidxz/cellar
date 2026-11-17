"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { type Protocol, READOUT_DATA_TYPE_LABELS, type ReadoutDataType } from "../../types";

/** Run conditions live alongside their definitions and control settings on Setup. */
export function ProtocolConditionsCard({
  protocol,
  canAdd,
  canEdit,
  onAdd,
  onEdit,
  onRemove,
}: {
  protocol: Protocol;
  canAdd: boolean;
  canEdit: boolean;
  onAdd: () => void;
  onEdit: (id: string) => void;
  onRemove: (id: string) => void;
}) {
  const conditions = protocol.condition_definitions;
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
        <div className="grid gap-1">
          <CardTitle>Assay conditions</CardTitle>
          <CardDescription>
            Recorded with every run; they tell its runs apart. Define each condition and its allowed
            values here.
          </CardDescription>
        </div>
        {canAdd && (
          <Button variant="outline" size="sm" onClick={onAdd}>
            <Plus className="size-4" /> Add condition
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {conditions.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            None yet. Add what each run records, such as concentrations, times, or temperatures.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Data Type</TableHead>
                <TableHead>Unit</TableHead>
                <TableHead>Allowed values</TableHead>
                <TableHead>Fixed value</TableHead>
                {canEdit && (
                  <TableHead className="w-20">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {conditions.map((cd) => (
                <TableRow key={cd.id}>
                  <TableCell className="font-medium">{cd.name}</TableCell>
                  <TableCell>
                    {READOUT_DATA_TYPE_LABELS[cd.data_type as ReadoutDataType] ?? cd.data_type}
                  </TableCell>
                  <TableCell>{cd.unit || "—"}</TableCell>
                  <TableCell className="whitespace-normal">
                    {cd.pick_list_values?.join(", ") || "—"}
                  </TableCell>
                  <TableCell>
                    {cd.fixed_value
                      ? `${cd.fixed_value}${cd.unit ? ` ${cd.unit}` : ""}`
                      : "Varies per run"}
                  </TableCell>
                  {canEdit && (
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Edit ${cd.name}`}
                          onClick={() => onEdit(cd.id)}
                        >
                          <Pencil className="size-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className="text-destructive hover:text-destructive"
                          aria-label={`Delete ${cd.name}`}
                          onClick={() => onRemove(cd.id)}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {protocol.status === "active" && (
          <p className="text-xs text-muted-foreground">
            Add new conditions here. Edit existing definitions and allowed values in a draft or new
            version. Change a fixed value with Correct details.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
