"use client";

import { StatusBadge } from "@/shared/components/status-badge";
import { Badge } from "@/shared/components/ui/badge";
import { protocolTextMatch } from "../lib/protocol-facets";
import { PROTOCOL_TYPE_LABELS, type Protocol } from "../types";
import { TargetChips } from "./target-chips";

interface ProtocolLibraryRowProps {
  protocol: Protocol;
  onSelect?: (protocolId: string) => void;
  /** Active library search; a non-name hit says which field matched. */
  search?: string;
}

const NAME_FLAG_BADGE: Record<string, string> = {
  needs_facts: "incomplete name",
  needs_discriminator: "needs discriminator",
  name_conflict: "name conflict",
};

export function ProtocolLibraryRow({ protocol, onSelect, search }: ProtocolLibraryRowProps) {
  const match = search ? protocolTextMatch(protocol, search) : null;
  return (
    <button
      type="button"
      onClick={() => onSelect?.(protocol.id)}
      className="flex w-full items-center gap-3 rounded-md border-b px-3 py-2 text-left text-sm hover:bg-muted"
    >
      <span className="w-24 shrink-0 font-mono text-xs text-muted-foreground">{protocol.code}</span>
      <span className="min-w-0 flex-1 truncate">
        <span className="font-medium">{protocol.name}</span>
        {protocol.name_flag && (
          <Badge variant="warning" className="ml-2">
            {NAME_FLAG_BADGE[protocol.name_flag] ?? protocol.name_flag}
          </Badge>
        )}
        {match && match.field !== "name" && (
          <span className="ml-2 text-xs text-muted-foreground">
            matched {match.field}: {match.value}
          </span>
        )}
      </span>
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
