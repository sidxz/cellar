"use client";

import { EmptyState } from "@/shared/components/empty-state";
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
import { ChevronDown, TestTubes } from "lucide-react";
import { PROTOCOL_SORT_OPTIONS, type ProtocolSort } from "../lib/protocol-dates";
import { GROUP_BY_OPTIONS, type GroupBy, type ProtocolGroup } from "../lib/protocol-facets";
import type { Protocol } from "../types";
import { ProtocolLibraryRow } from "./protocol-library-row";

interface GroupedProtocolListProps {
  groups: ProtocolGroup[];
  sort?: ProtocolSort;
  onSortChange?: (sort: ProtocolSort) => void;
  datesLoading?: boolean;
  datesError?: boolean;
  groupBy: GroupBy;
  onGroupByChange: (g: GroupBy) => void;
  onSelect?: (protocolId: string) => void;
  search?: string;
  onNewFrom?: (protocol: Protocol) => void;
}

export function GroupedProtocolList({
  groups,
  sort = "last_run_desc",
  onSortChange,
  datesLoading = false,
  datesError = false,
  groupBy,
  onGroupByChange,
  onSelect,
  search,
  onNewFrom,
}: GroupedProtocolListProps) {
  const total = groups.reduce((n, g) => n + g.count, 0);
  return (
    <div className="min-w-0 flex-1 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm text-muted-foreground">{total} shown</span>
        <div className="flex flex-wrap items-center gap-3">
          {onSortChange && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-muted-foreground">
                {groupBy === "none" ? "Sort by" : "Sort within groups"}
              </span>
              <Select value={sort} onValueChange={(v) => onSortChange(v as ProtocolSort)}>
                <SelectTrigger size="sm" className="w-48" aria-label="Sort protocols">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROTOCOL_SORT_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-muted-foreground">Group by</span>
            <Select value={groupBy} onValueChange={(v) => onGroupByChange(v as GroupBy)}>
              <SelectTrigger size="sm" className="w-[160px]" aria-label="Group protocols by">
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
      </div>

      {groups.length === 0 && (
        <EmptyState
          icon={TestTubes}
          title="No matching protocols"
          description="Try a different search or clear filters to broaden the list."
        />
      )}
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
              <ProtocolLibraryRow
                key={p.id}
                protocol={p}
                datesLoading={datesLoading}
                datesError={datesError}
                onSelect={onSelect}
                search={search}
                onNewFrom={onNewFrom}
              />
            ))}
          </CollapsibleContent>
        </Collapsible>
      ))}
    </div>
  );
}
