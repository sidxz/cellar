"use client";

import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Settings2 } from "lucide-react";
import { Fragment } from "react";
import type { ConditionDefinition, Protocol } from "../../types";

/** What a condition holds: its fixed value (it defines the protocol), or what each run enters. */
function conditionValue(cd: ConditionDefinition) {
  const unit = cd.unit?.trim();
  if (cd.fixed_value) return `${cd.fixed_value}${unit ? ` ${unit}` : ""}`;
  const options = cd.pick_list_values?.length ? `one of ${cd.pick_list_values.join(", ")}` : unit;
  return (
    <span className="italic text-muted-foreground">
      varies per run{options ? ` (${options})` : ""}
    </span>
  );
}

/** Every condition the protocol records, right under the method: concentrations, times and
 *  temperatures are what make its runs comparable. Edited on the Design tab. */
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
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle>Assay conditions</CardTitle>
        <Button variant="ghost" size="sm" className="h-auto px-2 py-1" onClick={onOpenDesign}>
          <Settings2 className="mr-1.5 h-3.5 w-3.5" />
          Open in Design
        </Button>
      </CardHeader>
      <CardContent>
        {conditions.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No conditions recorded. Concentrations, times and temperatures are added in Design.
          </p>
        ) : (
          <dl className="grid grid-cols-[minmax(0,max-content)_1fr] gap-x-6 gap-y-1.5 text-sm">
            {conditions.map((cd) => (
              <Fragment key={cd.id}>
                <dt className="text-muted-foreground">{cd.name}</dt>
                <dd className="font-medium">{conditionValue(cd)}</dd>
              </Fragment>
            ))}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}
