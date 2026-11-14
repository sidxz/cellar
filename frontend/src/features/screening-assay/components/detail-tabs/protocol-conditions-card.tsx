"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Settings2 } from "lucide-react";
import { Fragment } from "react";
import type { ConditionDefinition, Protocol } from "../../types";

/** What a run enters for the condition (its unit, or the allowed values), or, the exception,
 *  the one value every run uses. */
function conditionDetail(cd: ConditionDefinition): string {
  const unit = cd.unit?.trim();
  if (cd.fixed_value) return `Fixed: ${cd.fixed_value}${unit ? ` ${unit}` : ""}`;
  if (cd.pick_list_values?.length) return cd.pick_list_values.join(", ");
  return unit ?? "";
}

/** The conditions each run records, right under the method: they tell the protocol's runs apart
 *  and together define it. Edited on the Design tab. */
export function ProtocolConditionsCard({
  protocol,
  onOpenDesign,
}: {
  protocol: Protocol;
  onOpenDesign: () => void;
}) {
  const conditions = protocol.condition_definitions;
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
        <div className="grid gap-1">
          <CardTitle>Assay conditions</CardTitle>
          <CardDescription>Recorded with every run; they tell its runs apart.</CardDescription>
        </div>
        <Button variant="ghost" size="sm" className="h-auto px-2 py-1" onClick={onOpenDesign}>
          <Settings2 className="mr-1.5 h-3.5 w-3.5" />
          Open in Design
        </Button>
      </CardHeader>
      <CardContent>
        {conditions.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            None yet. Add what each run records (concentrations, times, temperatures) in Design.
          </p>
        ) : (
          <dl className="grid grid-cols-[minmax(0,max-content)_1fr] gap-x-6 gap-y-1.5 text-sm">
            {conditions.map((cd) => (
              <Fragment key={cd.id}>
                <dt className="font-medium">{cd.name}</dt>
                <dd className="text-muted-foreground">{conditionDetail(cd)}</dd>
              </Fragment>
            ))}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
