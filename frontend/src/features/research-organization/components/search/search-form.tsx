"use client";

import { useState, useEffect, useCallback } from "react";
import { Search, RotateCcw } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import { Separator } from "@/shared/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import type {
  SearchQuery,
  SearchCriterion,
  ActivityCriterion,
  TextCriterion,
  PropertyCriterion,
  StructureCriterion,
} from "../../types";
import { ProtocolSection } from "./protocol-section";
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

// ─── Props ──────────────────────────────────────────────────────────────────

interface SearchFormProps {
  initialQuery?: SearchQuery;
  onSearch: (query: SearchQuery, protocolColumns: string[]) => void;
  isLoading?: boolean;
}

// ─── Helpers: decompose SearchQuery into section states ─────────────────────

function decomposeQuery(query: SearchQuery | undefined) {
  const activityCriteria: ActivityCriterion[] = [];
  const textCriteria: TextCriterion[] = [];
  const propertyCriteria: PropertyCriterion[] = [];
  let structureCriterion: StructureCriterion | null = null;
  const collectionCriteria: SearchCriterion[] = [];
  const advanced: AdvancedFiltersState = emptyAdvancedFilters();

  if (!query) {
    return { activityCriteria, textCriteria, propertyCriteria, structureCriterion, collectionCriteria, advanced, logic: "and" as const };
  }

  for (const c of query.criteria) {
    switch (c.type) {
      case "activity":
        activityCriteria.push(c);
        break;
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
      // group and project criteria are not decomposed into sections
      default:
        break;
    }
  }

  return {
    activityCriteria,
    textCriteria,
    propertyCriteria,
    structureCriterion,
    collectionCriteria,
    advanced,
    logic: query.logic,
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

export function SearchForm({ initialQuery, onSearch, isLoading }: SearchFormProps) {
  // Parse initial query into section states
  const initial = decomposeQuery(initialQuery);

  const [logic, setLogic] = useState<"and" | "or">(initial.logic ?? "and");
  const [activityCriteria, setActivityCriteria] = useState<ActivityCriterion[]>(initial.activityCriteria);
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
    setLogic(parsed.logic ?? "and");
    setActivityCriteria(parsed.activityCriteria);
    setStructureCriterion(parsed.structureCriterion);
    setPropertyCriteria(parsed.propertyCriteria);
    setCollectionTerms(collectionCriteriaToTerms(parsed.collectionCriteria));
    setTextCriteria(parsed.textCriteria);
    setAdvanced(parsed.advanced);
  }, [initialQuery]);

  // Compose all section states back into a SearchQuery
  const composeCriteria = useCallback((): SearchCriterion[] => {
    const criteria: SearchCriterion[] = [];

    // Activity
    for (const c of activityCriteria) {
      if (c.protocol_id) criteria.push(c);
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
  }, [activityCriteria, structureCriterion, propertyCriteria, collectionTerms, textCriteria, advanced]);

  function handleSearch() {
    const criteria = composeCriteria();
    const query: SearchQuery = { criteria, logic };
    const protocolColumns = deriveProtocolColumns(activityCriteria);
    onSearch(query, protocolColumns);
  }

  function handleReset() {
    setLogic("and");
    setActivityCriteria([]);
    setStructureCriterion(null);
    setPropertyCriteria([]);
    setCollectionTerms([]);
    setTextCriteria([]);
    setAdvanced(emptyAdvancedFilters());
  }

  const totalCriteria = composeCriteria().length;

  return (
    <div className="space-y-4 rounded-lg border p-4">
      {/* Header: logic toggle + search button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Label className="text-sm text-muted-foreground">Match</Label>
          <Select value={logic} onValueChange={(v) => setLogic(v as "and" | "or")}>
            <SelectTrigger className="h-8 w-20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="and">AND</SelectItem>
              <SelectItem value="or">OR</SelectItem>
            </SelectContent>
          </Select>
          <Label className="text-sm text-muted-foreground">of the following criteria</Label>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleReset}
            disabled={isLoading}
          >
            <RotateCcw className="mr-1 h-3.5 w-3.5" />
            Reset
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={handleSearch}
            disabled={isLoading}
          >
            <Search className="mr-1 h-3.5 w-3.5" />
            {isLoading ? "Searching..." : `Search${totalCriteria > 0 ? ` (${totalCriteria})` : ""}`}
          </Button>
        </div>
      </div>

      {/* 2-column grid for main sections */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Left column: Protocol + Properties */}
        <div className="space-y-4">
          <ProtocolSection criteria={activityCriteria} onChange={setActivityCriteria} />
          <Separator />
          <PropertySection criteria={propertyCriteria} onChange={setPropertyCriteria} />
        </div>

        {/* Right column: Structure + Collections + Keywords */}
        <div className="space-y-4">
          <StructureSection criterion={structureCriterion} onChange={setStructureCriterion} />
          <Separator />
          <CollectionSection terms={collectionTerms} onChange={setCollectionTerms} />
          <Separator />
          <KeywordSection criteria={textCriteria} onChange={setTextCriteria} />
        </div>
      </div>

      {/* Expandable advanced section */}
      <Separator />
      <AdvancedFilters state={advanced} onChange={setAdvanced} />
    </div>
  );
}
