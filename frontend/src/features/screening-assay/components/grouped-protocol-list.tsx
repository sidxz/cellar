"use client";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { ChevronDown } from "lucide-react";
import { GROUP_BY_OPTIONS, type GroupBy, type ProtocolGroup } from "../lib/protocol-facets";
import { ProtocolLibraryRow } from "./protocol-library-row";

interface GroupedProtocolListProps {
  groups: ProtocolGroup[];
  groupBy: GroupBy;
  onGroupByChange: (g: GroupBy) => void;
  onSelect?: (protocolId: string) => void;
}

export function GroupedProtocolList({
  groups,
  groupBy,
  onGroupByChange,
  onSelect,
}: GroupedProtocolListProps) {
  const total = groups.reduce((n, g) => n + g.count, 0);
  return (
    <div className="min-w-0 flex-1 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{total} shown</span>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Group by</span>
          <Select value={groupBy} onValueChange={(v) => onGroupByChange(v as GroupBy)}>
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {GROUP_BY_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {groups.map((group) => (
        <Collapsible key={group.key} defaultOpen className="rounded-md border">
          <CollapsibleTrigger className="flex w-full items-center justify-between bg-muted/50 px-3 py-2 text-sm font-medium">
            <span className="flex items-center gap-2">
              <ChevronDown className="h-4 w-4" />
              {group.label}
            </span>
            <span className="text-xs tabular-nums text-muted-foreground">{group.count}</span>
          </CollapsibleTrigger>
          <CollapsibleContent>
            {group.protocols.map((p) => (
              <ProtocolLibraryRow key={p.id} protocol={p} onSelect={onSelect} />
            ))}
          </CollapsibleContent>
        </Collapsible>
      ))}
    </div>
  );
}
