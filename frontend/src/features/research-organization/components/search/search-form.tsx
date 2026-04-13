"use client";

import { useState, useEffect, useCallback } from "react";
import { Search, RotateCcw } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Separator } from "@/shared/components/ui/separator";
import type {
  SearchQuery,
  SearchCriterion,
  ActivityCriterion,
  GroupCriterion,
  TextCriterion,
  PropertyCriterion,
  StructureCriterion,
} from "../../types";
import { ProtocolSection, type ProtocolConjunction } from "./protocol-section";
import { StructureSection } from "./structure-section";
import { PropertySection } from "./property-section";
import {
  CollectionSection,
  termsToCollectionCriteria,
  collectionCriteriaToTerms,
  type CollectionTermValue,
} from "./collection-section";
import { KeywordSection } from "./keyword-section";
import {
  AdvancedFilters,
  emptyAdvancedFilters,
  type AdvancedFiltersState,
} from "./advanced-filters";
import { ProjectFilter } from "./project-filter";

// ─── Props ──────────────────────────────────────────────────────────────────

interface SearchFormProps {
  initialQuery?: SearchQuery;
  projectIds: string[];
  onProjectsChange: (ids: string[]) => void;
  onSearch: (query: SearchQuery, protocolColumns: string[]) => void;
  isLoading?: boolean;
}

// ─── Helpers: decompose SearchQuery into section states ─────────────────────

function decomposeQuery(query: SearchQuery | undefined) {
  const activityCriteria: ActivityCriterion[] = [];
  const protocolConjunctions: ProtocolConjunction[] = [];
  const textCriteria: TextCriterion[] = [];
  const propertyCriteria: PropertyCriterion[] = [];
  let structureCriterion: StructureCriterion | null = null;
  const collectionCriteria: SearchCriterion[] = [];
  const advanced: AdvancedFiltersState = emptyAdvancedFilters();

  if (!query) {
    return { activityCriteria, protocolConjunctions, textCriteria, propertyCriteria, structureCriterion, collectionCriteria, advanced };
  }

  for (const c of query.criteria) {
    switch (c.type) {
      case "activity":
        // Top-level activity criteria were ANDed
        protocolConjunctions.push(activityCriteria.length === 0 ? "and" : "and");
        activityCriteria.push(c);
        break;
      case "group": {
        // GroupCriterion with activity criteria — extract with the group's logic
        const group = c as GroupCriterion;
        for (const gc of group.criteria) {
          if (gc.type === "activity") {
            // First item in group gets conjunction from context; rest get group logic
            protocolConjunctions.push(
              activityCriteria.length === 0 ? group.logic : group.logic,
            );
            activityCriteria.push(gc as ActivityCriterion);
          }
        }
        break;
      }
      case "text":
        textCriteria.push(c);
        break;
      case "property":
        propertyCriteria.push(c);
        break;
      case "structure":
        structureCriterion = c;
        break;
      case "collection":
        collectionCriteria.push(c);
        break;
      case "selectivity":
        advanced.selectivity.push(c);
        break;
      case "batch":
        advanced.batch.push(c);
        break;
      case "run_date":
        advanced.runDate.push(c);
        break;
      case "custom_field":
        advanced.customFields.push(c);
        break;
      case "keyword_list":
        advanced.keywordLists.push(c);
        break;
      default:
        break;
    }
  }

  return {
    activityCriteria,
    protocolConjunctions,
    textCriteria,
    propertyCriteria,
    structureCriterion,
    collectionCriteria,
    advanced,
  };
}

/** Derive protocol column IDs from activity criteria for cross-protocol display. */
function deriveProtocolColumns(activityCriteria: ActivityCriterion[]): string[] {
  const columns: string[] = [];
  for (const c of activityCriteria) {
    if (!c.protocol_id) continue;
    const curveType = c.curve_type ?? "ic50";
    const colId = `drc:${c.protocol_id}:${curveType}`;
    if (!columns.includes(colId)) columns.push(colId);
  }
  return columns;
}

// ─── Component ──────────────────────────────────────────────────────────────

export function SearchForm({
  initialQuery,
  projectIds,
  onProjectsChange,
  onSearch,
  isLoading,
}: SearchFormProps) {
  // Parse initial query into section states
  const initial = decomposeQuery(initialQuery);

  const [activityCriteria, setActivityCriteria] = useState<ActivityCriterion[]>(initial.activityCriteria);
  const [protocolConjunctions, setProtocolConjunctions] = useState<ProtocolConjunction[]>(
    initial.protocolConjunctions.length > 0
      ? initial.protocolConjunctions
      : initial.activityCriteria.map(() => "or" as ProtocolConjunction)
  );
  const [structureCriterion, setStructureCriterion] = useState<StructureCriterion | null>(initial.structureCriterion);
  const [propertyCriteria, setPropertyCriteria] = useState<PropertyCriterion[]>(initial.propertyCriteria);
  const [collectionTerms, setCollectionTerms] = useState<CollectionTermValue[]>(
    collectionCriteriaToTerms(initial.collectionCriteria)
  );
  const [textCriteria, setTextCriteria] = useState<TextCriterion[]>(initial.textCriteria);
  const [advanced, setAdvanced] = useState<AdvancedFiltersState>(initial.advanced);

  // Re-parse when initialQuery changes externally (e.g., loading a saved search)
  useEffect(() => {
    const parsed = decomposeQuery(initialQuery);
    setActivityCriteria(parsed.activityCriteria);
    setProtocolConjunctions(
      parsed.protocolConjunctions.length > 0
        ? parsed.protocolConjunctions
        : parsed.activityCriteria.map(() => "or" as ProtocolConjunction)
    );
    setStructureCriterion(parsed.structureCriterion);
    setPropertyCriteria(parsed.propertyCriteria);
    setCollectionTerms(collectionCriteriaToTerms(parsed.collectionCriteria));
    setTextCriteria(parsed.textCriteria);
    setAdvanced(parsed.advanced);
  }, [initialQuery]);

  // Compose all section states back into a SearchQuery
  const composeCriteria = useCallback((): SearchCriterion[] => {
    const criteria: SearchCriterion[] = [];

    // Activity — respect per-row conjunctions
    // Filter to valid criteria and their matching conjunctions
    const validIndices = activityCriteria
      .map((c, i) => (c.protocol_id ? i : -1))
      .filter((i) => i >= 0);
    const validActivity = validIndices.map((i) => activityCriteria[i]);
    const validConjs = validIndices.map((i) => protocolConjunctions[i] ?? "or");

    if (validActivity.length === 1) {
      criteria.push(validActivity[0]);
    } else if (validActivity.length > 1) {
      const allAnd = validConjs.every((c) => c === "and");
      const allOr = validConjs.slice(1).every((c) => c === "or"); // first row has no conjunction
      if (allAnd) {
        // All "and" — push individually (top-level AND)
        for (const c of validActivity) criteria.push(c);
      } else if (allOr) {
        // All "or" — single group
        criteria.push({ type: "group", logic: "or", criteria: validActivity });
      } else {
        // Mixed — group consecutive "or" runs, AND between groups
        // e.g. A and B or C → [A] AND [group(or, B, C)]
        let currentGroup: typeof validActivity = [validActivity[0]];
        for (let i = 1; i < validActivity.length; i++) {
          if (validConjs[i] === "or") {
            currentGroup.push(validActivity[i]);
          } else {
            // Flush current group
            if (currentGroup.length === 1) {
              criteria.push(currentGroup[0]);
            } else {
              criteria.push({ type: "group", logic: "or", criteria: currentGroup });
            }
            currentGroup = [validActivity[i]];
          }
        }
        // Flush last group
        if (currentGroup.length === 1) {
          criteria.push(currentGroup[0]);
        } else {
          criteria.push({ type: "group", logic: "or", criteria: currentGroup });
        }
      }
    }

    // Structure
    if (structureCriterion) {
      const hasValue =
        (structureCriterion.search_type === "substructure" && structureCriterion.smarts && structureCriterion.smarts.length > 0) ||
        (structureCriterion.search_type === "similarity" && structureCriterion.smiles && structureCriterion.smiles.length > 0) ||
        (structureCriterion.search_type === "exact" && structureCriterion.inchi_key && structureCriterion.inchi_key.length > 0);
      if (hasValue) criteria.push(structureCriterion);
    }

    // Properties
    for (const c of propertyCriteria) {
      criteria.push(c);
    }

    // Collections
    for (const c of termsToCollectionCriteria(collectionTerms)) {
      criteria.push(c);
    }

    // Text / Keywords
    for (const c of textCriteria) {
      if (c.value) criteria.push(c);
    }

    // Advanced: selectivity
    for (const c of advanced.selectivity) {
      if (c.target_protocol_id && c.counter_protocol_id) criteria.push(c);
    }

    // Advanced: batch
    for (const c of advanced.batch) {
      criteria.push(c);
    }

    // Advanced: run date
    for (const c of advanced.runDate) {
      if (c.date_from || c.date_to) criteria.push(c);
    }

    // Advanced: custom fields
    for (const c of advanced.customFields) {
      if (c.field) criteria.push(c);
    }

    // Advanced: keyword lists
    for (const c of advanced.keywordLists) {
      if (c.values.length > 0) criteria.push(c);
    }

    return criteria;
  }, [activityCriteria, protocolConjunctions, structureCriterion, propertyCriteria, collectionTerms, textCriteria, advanced]);

  function handleSearch() {
    const criteria = composeCriteria();
    const query: SearchQuery = { criteria, logic: "and" };
    const protocolColumns = deriveProtocolColumns(activityCriteria);
    onSearch(query, protocolColumns);
  }

  function handleReset() {
    setActivityCriteria([]);
    setProtocolConjunctions([]);
    setStructureCriterion(null);
    setPropertyCriteria([]);
    setCollectionTerms([]);
    setTextCriteria([]);
    setAdvanced(emptyAdvancedFilters());
    onProjectsChange([]);
  }

  const criteriaCount = composeCriteria().length;

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      {/* Header: projects + actions */}
      <div className="flex items-center justify-between mb-3 pb-3 border-b border-border">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex-shrink-0">
            Projects
          </span>
          <ProjectFilter selectedIds={projectIds} onChange={onProjectsChange} />
        </div>
        <div className="flex gap-2 flex-shrink-0 ml-4">
          <Button variant="ghost" size="sm" onClick={handleReset}>
            <RotateCcw className="h-3.5 w-3.5 mr-1.5" /> Reset
          </Button>
          <Button size="sm" onClick={handleSearch} disabled={isLoading}>
            <Search className="h-3.5 w-3.5 mr-1.5" />
            Search
            {criteriaCount > 0 && (
              <span className="ml-1.5 rounded-full bg-white/20 px-1.5 text-[10px]">
                {criteriaCount}
              </span>
            )}
          </Button>
        </div>
      </div>

      {/* Protocols — full width */}
      <ProtocolSection
        criteria={activityCriteria}
        conjunctions={protocolConjunctions}
        onChange={(criteria, conjs) => {
          setActivityCriteria(criteria);
          setProtocolConjunctions(conjs);
        }}
      />

      <Separator className="my-3" />

      {/* Structure | Properties — two columns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-8 gap-y-4">
        <StructureSection criterion={structureCriterion} onChange={setStructureCriterion} />
        <PropertySection criteria={propertyCriteria} onChange={setPropertyCriteria} />
      </div>

      <Separator className="my-3" />

      {/* Collections | Keywords — two columns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-8 gap-y-4">
        <CollectionSection terms={collectionTerms} onChange={setCollectionTerms} />
        <KeywordSection criteria={textCriteria} onChange={setTextCriteria} />
      </div>

      {/* More Filters */}
      <div className="mt-3 pt-3 border-t border-border">
        <AdvancedFilters state={advanced} onChange={setAdvanced} />
      </div>
    </div>
  );
}
