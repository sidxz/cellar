"use client";

import { useState } from "react";
import { useProtocolFacets } from "../hooks/use-protocol-facets";
import type { FacetDimension, FacetSelections, GroupBy } from "../lib/protocol-facets";
import type { Protocol } from "../types";
import { FacetSidebar } from "./facet-sidebar";
import { GroupedProtocolList } from "./grouped-protocol-list";

interface ProtocolLibraryViewProps {
  protocols: Protocol[];
  onSelect?: (protocolId: string) => void;
}

export function ProtocolLibraryView({ protocols, onSelect }: ProtocolLibraryViewProps) {
  const hasRetired = protocols.some((p) => p.status === "retired");
  // Default: pre-exclude retired (only when some exist, else no status preset).
  const [selections, setSelections] = useState<FacetSelections>(() =>
    hasRetired ? { status: new Set<string>(["draft", "active"]) } : {},
  );
  const [groupBy, setGroupBy] = useState<GroupBy>("target");
  const { facetModel, groups } = useProtocolFacets(protocols, selections, groupBy);

  const toggle = (dim: FacetDimension, value: string) => {
    setSelections((prev) => {
      const next: FacetSelections = { ...prev };
      const set = new Set(next[dim] ?? []);
      if (set.has(value)) set.delete(value);
      else set.add(value);
      if (set.size === 0) delete next[dim];
      else next[dim] = set;
      return next;
    });
  };

  return (
    <div className="flex gap-4">
      <FacetSidebar
        model={facetModel}
        selections={selections}
        onToggle={toggle}
        onClear={() => setSelections({})}
      />
      <GroupedProtocolList
        groups={groups}
        groupBy={groupBy}
        onGroupByChange={setGroupBy}
        onSelect={onSelect}
      />
    </div>
  );
}
