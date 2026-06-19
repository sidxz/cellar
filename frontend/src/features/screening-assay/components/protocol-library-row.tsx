"use client";

import { StatusBadge } from "@/shared/components/status-badge";
import { PROTOCOL_TYPE_LABELS, type Protocol } from "../types";
import { TargetChips } from "./target-chips";

interface ProtocolLibraryRowProps {
  protocol: Protocol;
  onSelect?: (protocolId: string) => void;
}

export function ProtocolLibraryRow({ protocol, onSelect }: ProtocolLibraryRowProps) {
  return (
    <button
      type="button"
      onClick={() => onSelect?.(protocol.id)}
      className="flex w-full items-center gap-3 rounded-md border-b px-3 py-2 text-left hover:bg-muted"
    >
      <span className="min-w-0 flex-1 truncate font-medium">{protocol.name}</span>
      <span className="w-28 shrink-0 text-xs text-muted-foreground">
        {PROTOCOL_TYPE_LABELS[protocol.protocol_type] ?? protocol.protocol_type}
      </span>
      <span className="hidden w-40 shrink-0 md:block">
        <TargetChips targets={protocol.targets} />
      </span>
      <span className="w-24 shrink-0 truncate text-xs text-muted-foreground">
        {protocol.category ?? ""}
      </span>
      <span className="w-14 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
        {protocol.readout_definitions.length} rd
      </span>
      <span className="w-20 shrink-0">
        <StatusBadge status={protocol.status} />
      </span>
    </button>
  );
}
