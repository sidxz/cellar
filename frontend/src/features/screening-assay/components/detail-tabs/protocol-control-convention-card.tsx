"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useUpdateProtocol } from "../../hooks/use-protocols";
import { POS_CONTROL_SIGNAL_LABELS, type PosControlSignal, type Protocol } from "../../types";

export function ProtocolControlConventionCard({
  protocol,
  protocolId,
}: { protocol: Protocol; protocolId: string }) {
  const updateProtocol = useUpdateProtocol(protocolId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Control Convention</CardTitle>
        <CardDescription>
          Tells the calculation engine which control well produces high raw signal. Drives %
          Inhibition / % Activation / % Control / Z-Score formula dispatch and the heatmap legend.
          Editable after publish — re-run Recompute on each run after changing.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-0 space-y-1">
            <Label className="text-xs">POS control signal</Label>
            <Select
              value={protocol.pos_control_signal}
              onValueChange={(v) => {
                if (v === protocol.pos_control_signal) return;
                updateProtocol.mutate({ pos_control_signal: v as PosControlSignal });
              }}
              disabled={protocol.status === "retired" || updateProtocol.isPending}
            >
              <SelectTrigger className="w-full sm:w-[420px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(["high", "low"] as PosControlSignal[]).map((v) => (
                  <SelectItem key={v} value={v}>
                    {POS_CONTROL_SIGNAL_LABELS[v]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {updateProtocol.isPending && (
            <span className="pb-2 text-xs text-muted-foreground">Saving…</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
