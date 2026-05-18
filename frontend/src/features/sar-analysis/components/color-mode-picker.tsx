"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/components/ui/select";
import type { ColorMode } from "@/features/sar-analysis/types";

export interface ProtocolOption {
  id: string;
  name: string;
}

interface ColorModePickerProps {
  mode: ColorMode;
  protocolId: string | null;
  protocols: ProtocolOption[];
  onChange: (mode: ColorMode, protocolId?: string) => void;
}

export function ColorModePicker({ mode, protocolId, protocols, onChange }: ColorModePickerProps) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-muted-foreground">Color by:</span>
      <Select
        value={mode}
        onValueChange={(v) => onChange(v as ColorMode, protocolId ?? protocols[0]?.id)}
      >
        <SelectTrigger className="h-8 w-32"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="cluster">Cluster</SelectItem>
          <SelectItem value="activity" disabled={protocols.length === 0}>Activity</SelectItem>
          <SelectItem value="scaffold">Scaffold</SelectItem>
          <SelectItem value="none">None</SelectItem>
        </SelectContent>
      </Select>
      {mode === "activity" && protocols.length > 0 && (
        <Select
          value={protocolId ?? protocols[0].id}
          onValueChange={(v) => onChange("activity", v)}
        >
          <SelectTrigger className="h-8 w-40"><SelectValue /></SelectTrigger>
          <SelectContent>
            {protocols.map((p) => (
              <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </div>
  );
}
