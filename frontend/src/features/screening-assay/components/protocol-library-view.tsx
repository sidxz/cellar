"use client";

import { useTermsInUse } from "@/features/workspace-config/hooks/use-ontology-search";
import { useMemo, useState } from "react";
import { useProtocolFacets } from "../hooks/use-protocol-facets";
import {
  type FacetDimension,
  type FacetSelections,
  GROUP_BY_OPTIONS,
  type GroupBy,
  type ShortLabels,
  shortLabelLookup,
} from "../lib/protocol-facets";
import type { Protocol } from "../types";
import { FacetSidebar } from "./facet-sidebar";
import { GroupedProtocolList } from "./grouped-protocol-list";

const GROUP_BY_KEY = "protocol-library-group-by";
const DEFAULT_GROUP_BY: GroupBy = "category";

function readGroupBy(): GroupBy {
  try {
    const v = localStorage.getItem(GROUP_BY_KEY);
    return GROUP_BY_OPTIONS.some((o) => o.value === v) ? (v as GroupBy) : DEFAULT_GROUP_BY;
  } catch {
    return DEFAULT_GROUP_BY;
  }
}

function useShortLabels(): ShortLabels {
  const organism = useTermsInUse("organism").data;
  const cellLine = useTermsInUse("cell_line").data;
  const strain = useTermsInUse("strain").data;
  return useMemo(
    () => ({
      organism: shortLabelLookup(organism ?? []),
      cell_line: shortLabelLookup(cellLine ?? []),
      strain: shortLabelLookup(strain ?? []),
    }),
    [organism, cellLine, strain],
  );
}

interface ProtocolLibraryViewProps {
  protocols: Protocol[];
  onSelect?: (protocolId: string) => void;
  search?: string;
}

export function ProtocolLibraryView({ protocols, onSelect, search }: ProtocolLibraryViewProps) {
  const hasRetired = protocols.some((p) => p.status === "retired");
  // Default: pre-exclude retired (only when some exist, else no status preset).
  const [selections, setSelections] = useState<FacetSelections>(() =>
    hasRetired ? { status: new Set<string>(["draft", "active"]) } : {},
  );
  const [groupBy, setGroupBy] = useState<GroupBy>(readGroupBy);
  const shortLabels = useShortLabels();
  const { facetModel, groups } = useProtocolFacets(protocols, selections, groupBy, shortLabels);

  const changeGroupBy = (g: GroupBy) => {
    setGroupBy(g);
    try {
      localStorage.setItem(GROUP_BY_KEY, g);
    } catch {
      // Storage unavailable: the choice just doesn't persist.
    }
  };

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
        onGroupByChange={changeGroupBy}
        onSelect={onSelect}
        search={search}
      />
    </div>
  );
}
