"use client";

import { useTermsInUse } from "@/features/workspace-config/hooks/use-ontology-search";
import { type Dispatch, type SetStateAction, useMemo, useState } from "react";
import { useProtocolFacets } from "../hooks/use-protocol-facets";
import {
  PROTOCOL_SORT_OPTIONS,
  type ProtocolSort,
  sortProtocolGroups,
} from "../lib/protocol-dates";
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

const SORT_KEY = "protocol-library-sort";
function readSort(): ProtocolSort {
  try {
    const saved = localStorage.getItem(SORT_KEY);
    return PROTOCOL_SORT_OPTIONS.some((o) => o.value === saved)
      ? (saved as ProtocolSort)
      : "last_run_desc";
  } catch {
    return "last_run_desc";
  }
}

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
  datesLoading?: boolean;
  datesError?: boolean;
  onSelect?: (protocolId: string) => void;
  search?: string;
  onNewFrom?: (protocol: Protocol) => void;
  selections?: FacetSelections;
  onSelectionsChange?: Dispatch<SetStateAction<FacetSelections>>;
}

export function ProtocolLibraryView({
  protocols,
  datesLoading = false,
  datesError = false,
  onSelect,
  search,
  onNewFrom,
  selections: controlledSelections,
  onSelectionsChange,
}: ProtocolLibraryViewProps) {
  const hasRetired = protocols.some((p) => p.status === "retired");
  // Default: pre-exclude retired (only when some exist, else no status preset).
  const [localSelections, setLocalSelections] = useState<FacetSelections>(() =>
    hasRetired ? { status: new Set<string>(["draft", "active"]) } : {},
  );
  const selections = controlledSelections ?? localSelections;
  const setSelections = onSelectionsChange ?? setLocalSelections;
  const [groupBy, setGroupBy] = useState<GroupBy>(readGroupBy);
  const [sort, setSort] = useState<ProtocolSort>(readSort);
  const changeSort = (next: ProtocolSort) => {
    setSort(next);
    try {
      localStorage.setItem(SORT_KEY, next);
    } catch {
      /* Session-only preference. */
    }
  };
  const shortLabels = useShortLabels();
  const { facetModel, groups } = useProtocolFacets(protocols, selections, groupBy, shortLabels);

  const sortedGroups = useMemo(() => sortProtocolGroups(groups, sort), [groups, sort]);

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
    <div className="flex flex-col gap-3 p-3 md:flex-row">
      <FacetSidebar
        model={facetModel}
        selections={selections}
        onToggle={toggle}
        onClear={() => setSelections({})}
      />
      <GroupedProtocolList
        groups={sortedGroups}
        sort={sort}
        onSortChange={changeSort}
        datesLoading={datesLoading}
        datesError={datesError}
        groupBy={groupBy}
        onGroupByChange={changeGroupBy}
        onSelect={onSelect}
        search={search}
        onNewFrom={onNewFrom}
      />
    </div>
  );
}
