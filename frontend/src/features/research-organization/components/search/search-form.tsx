"use client";

import type { Protocol } from "@/features/screening-assay/types";
import { Button } from "@/shared/components/ui/button";
import { Separator } from "@/shared/components/ui/separator";
import { RotateCcw, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchCount } from "../../hooks/use-search-count";
import { drcColId, rdColId } from "../../lib/protocol-column-id";
import type {
  ActivityCriterion,
  GroupCriterion,
  PropertyCriterion,
  ScaffoldCriterion,
  SearchCriterion,
  SearchQuery,
  StructureCriterion,
  TextCriterion,
} from "../../types";
import {
  AdvancedFilters,
  type AdvancedFiltersState,
  emptyAdvancedFilters,
} from "./advanced-filters";
import {
  CollectionSection,
  type CollectionTermValue,
  collectionCriteriaToTerms,
  termsToCollectionCriteria,
} from "./collection-section";
import { KeywordSection } from "./keyword-section";
import { ProjectFilter } from "./project-filter";
import { PropertySection } from "./property-section";
import { type ProtocolConjunction, ProtocolSection } from "./protocol-section";
import { ScaffoldSection } from "./scaffold-section";
import { StructureSection } from "./structure-section";
import {
  TagSection,
  type TagSectionValue,
  defaultTagSectionValue,
  tagCriteriaToSection,
  tagSectionToCriteria,
} from "./tag-section";

// ─── Props ──────────────────────────────────────────────────────────────────

interface SearchFormProps {
  initialQuery?: SearchQuery;
  projectIds: string[];
  onProjectsChange: (ids: string[]) => void;
  onSearch: (query: SearchQuery, protocolColumns: string[]) => void;
  isLoading?: boolean;
  /** Full protocol records (with readout_definitions) — used to pick sensible
   *  default columns when a criterion filters by protocol only. */
  protocols: Protocol[];
}

// ─── Helpers: decompose SearchQuery into section states ─────────────────────

function decomposeQuery(query: SearchQuery | undefined) {
  const activityCriteria: ActivityCriterion[] = [];
  const protocolConjunctions: ProtocolConjunction[] = [];
  const textCriteria: TextCriterion[] = [];
  const propertyCriteria: PropertyCriterion[] = [];
  let structureCriterion: StructureCriterion | null = null;
  const collectionCriteria: SearchCriterion[] = [];
  const scaffoldCriteria: ScaffoldCriterion[] = [];
  const tagCriteria: SearchCriterion[] = [];
  const advanced: AdvancedFiltersState = emptyAdvancedFilters();
  // Hoisted out so saved searches that include a project criterion can
  // re-populate the project chips at the top of the panel.
  let projectIds: string[] = [];

  if (!query) {
    return {
      activityCriteria,
      protocolConjunctions,
      textCriteria,
      propertyCriteria,
      structureCriterion,
      collectionCriteria,
      scaffoldCriteria,
      tagCriteria,
      advanced,
      projectIds,
    };
  }

  for (const c of query.criteria) {
    switch (c.type) {
      case "project":
        projectIds = [...c.project_ids];
        break;
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
            protocolConjunctions.push(activityCriteria.length === 0 ? group.logic : group.logic);
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
      case "scaffold":
        scaffoldCriteria.push(c);
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
      case "tag":
        tagCriteria.push(c);
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
    scaffoldCriteria,
    tagCriteria,
    advanced,
    projectIds,
  };
}

/**
 * Derive protocol column IDs from activity criteria for cross-protocol display.
 *
 * Every where-row carries a readout-def UUID plus a ``source`` discriminator;
 * the column key folds those into the read-model's column spec format:
 *   - ``drc:{readout_definition_id}`` for DR-curve sources
 *   - ``rd:{protocol_id}:{readout_definition_id}`` for raw readout sources
 * When a criterion filters by protocol alone, ``defaultProtocolColumns`` falls
 * back to "show what the protocol actually emits" so we don't always default
 * to IC50 on a single-dose protocol.
 */
function deriveProtocolColumns(
  activityCriteria: ActivityCriterion[],
  protocols: Protocol[],
): string[] {
  const columns: string[] = [];
  function add(col: string) {
    if (!columns.includes(col)) columns.push(col);
  }
  for (const c of activityCriteria) {
    // ponytail: any-protocol rows (null) derive no columns — results show the
    // molecule list only. Add a cross-protocol "best potency" column if asked.
    if (!c.protocol_id) continue;
    const conds =
      Array.isArray(c.where) && c.where.length > 0
        ? c.where
        : c.readout_definition_id
          ? [{ source: c.source ?? "dr_curve", readout_definition_id: c.readout_definition_id }]
          : [];
    let addedAny = false;
    for (const cond of conds) {
      if (!cond.readout_definition_id) continue;
      if (cond.source === "readout_data") {
        add(rdColId(c.protocol_id, cond.readout_definition_id));
      } else {
        add(drcColId(cond.readout_definition_id));
      }
      addedAny = true;
    }
    if (!addedAny) {
      for (const col of defaultProtocolColumns(c.protocol_id, protocols)) {
        add(col);
      }
    }
  }
  return columns;
}

/**
 * Default grid columns for a protocol-only filter.
 *
 * Rules (in priority order):
 *   1. Dose-response readouts (`data_type === "dose_response"`) emit a `drc:`
 *      column per fit, keyed by whatever curve type the readout's
 *      `dose_response_config` declares (ic50 / ec50 / ki / …). The grid
 *      renders each `drc:` as a separate (value, plot) pair.
 *   2. If the protocol has no DR readouts, every numeric readout (raw or
 *      calculated) emits an `rd:` column in `display_order`. For readouts
 *      with `normalizations` configured (e.g. percent_inhibition, z_score)
 *      we surface the first normalization as the default view — chemists
 *      want "% Inhibition" in the grid, not the underlying raw signal.
 *      Readouts without normalizations stay on the raw layer.
 *   3. As a defensive last resort (protocol record missing or only
 *      text/pick-list/file/date readouts), keep the legacy IC50 fallback
 *      so a column still renders.
 */
function defaultProtocolColumns(protocolId: string, protocols: Protocol[]): string[] {
  const proto = protocols.find((p) => p.id === protocolId);
  if (!proto) return [];

  const ordered = [...proto.readout_definitions].sort((a, b) => a.display_order - b.display_order);

  // Every DR readout-def becomes its own column. A protocol with two DR
  // readouts of the same curve_type (target IC50 + counter IC50) now
  // surfaces two columns instead of merging them.
  const drcCols: string[] = [];
  for (const rd of ordered) {
    if (rd.data_type === "dose_response") {
      drcCols.push(drcColId(rd.id));
    }
  }
  if (drcCols.length > 0) return drcCols;

  const rdCols: string[] = [];
  for (const rd of ordered) {
    if (rd.data_type !== "numeric") continue;
    const primaryNorm = rd.normalizations?.find((n) => n !== "none");
    // The 4-segment `rd:<proto>:<rd>:<norm>` shape lives only on this
    // default-columns path; everywhere else stays on the 3-segment form.
    // Keep the inline template here rather than adding a `rdNormColId`
    // formatter just for this one site.
    if (primaryNorm) {
      rdCols.push(`${rdColId(protocolId, rd.id)}:${primaryNorm}`);
    } else {
      rdCols.push(rdColId(protocolId, rd.id));
    }
  }
  return rdCols;
}

// Walks the composed criteria tree looking for any similarity structure clause.
// We surface a "ranked list, top N shown" caption when one is present, since
// the count covers *candidates above the threshold* but the result panel only
// shows the top-K by similarity score.
function containsSimilarity(criteria: SearchCriterion[]): boolean {
  for (const c of criteria) {
    if (c.type === "structure" && c.search_type === "similarity") return true;
    if (c.type === "group") {
      const inner = (c as GroupCriterion).criteria;
      if (containsSimilarity(inner)) return true;
    }
  }
  return false;
}

// ─── Component ──────────────────────────────────────────────────────────────

export function SearchForm({
  initialQuery,
  projectIds,
  onProjectsChange,
  onSearch,
  isLoading,
  protocols,
}: SearchFormProps) {
  // Parse initial query into section states
  const initial = decomposeQuery(initialQuery);

  const [activityCriteria, setActivityCriteria] = useState<ActivityCriterion[]>(
    initial.activityCriteria,
  );
  const [protocolConjunctions, setProtocolConjunctions] = useState<ProtocolConjunction[]>(
    initial.protocolConjunctions.length > 0
      ? initial.protocolConjunctions
      : initial.activityCriteria.map(() => "or" as ProtocolConjunction),
  );
  const [structureCriterion, setStructureCriterion] = useState<StructureCriterion | null>(
    initial.structureCriterion,
  );
  const [propertyCriteria, setPropertyCriteria] = useState<PropertyCriterion[]>(
    initial.propertyCriteria,
  );
  const [collectionTerms, setCollectionTerms] = useState<CollectionTermValue[]>(
    collectionCriteriaToTerms(initial.collectionCriteria),
  );
  const [scaffoldCriteria, setScaffoldCriteria] = useState<ScaffoldCriterion[]>(
    initial.scaffoldCriteria,
  );
  const [textCriteria, setTextCriteria] = useState<TextCriterion[]>(initial.textCriteria);
  const [advanced, setAdvanced] = useState<AdvancedFiltersState>(initial.advanced);
  const [tagValue, setTagValue] = useState<TagSectionValue>(
    tagCriteriaToSection(initial.tagCriteria),
  );

  // Re-parse when initialQuery changes externally (e.g., loading a saved search).
  // We intentionally don't depend on projectIds / onProjectsChange — re-parse
  // is driven by saved-search loads only; current values are read inside.
  // biome-ignore lint/correctness/useExhaustiveDependencies: see comment above
  useEffect(() => {
    const parsed = decomposeQuery(initialQuery);
    setActivityCriteria(parsed.activityCriteria);
    setProtocolConjunctions(
      parsed.protocolConjunctions.length > 0
        ? parsed.protocolConjunctions
        : parsed.activityCriteria.map(() => "or" as ProtocolConjunction),
    );
    setStructureCriterion(parsed.structureCriterion);
    setPropertyCriteria(parsed.propertyCriteria);
    setCollectionTerms(collectionCriteriaToTerms(parsed.collectionCriteria));
    setScaffoldCriteria(parsed.scaffoldCriteria);
    setTextCriteria(parsed.textCriteria);
    setAdvanced(parsed.advanced);
    setTagValue(tagCriteriaToSection(parsed.tagCriteria));
    // Round-trip saved searches: a stored project criterion repopulates the
    // chip(s) at the top of the panel so the chemist sees the same scope they
    // saved with. Only push when it actually changed to avoid re-fetch loops.
    if (initialQuery) {
      const same =
        parsed.projectIds.length === projectIds.length &&
        parsed.projectIds.every((id, i) => id === projectIds[i]);
      if (!same) onProjectsChange(parsed.projectIds);
    }
  }, [initialQuery]);

  // Compose all section states back into a SearchQuery
  const composeCriteria = useCallback((): SearchCriterion[] => {
    const criteria: SearchCriterion[] = [];

    // Project scope — the chip(s) at the top of the panel scope the result
    // set itself, not just the picker dropdowns. Empty array means
    // workspace-wide and is omitted entirely from the query.
    if (projectIds.length > 0) {
      criteria.push({ type: "project", project_ids: projectIds });
    }

    // Activity — respect per-row conjunctions
    // Prune incomplete where[] rows (field missing, value missing for non-between, etc.)
    // so the backend never sees a half-filled condition.
    const cleanedActivity = activityCriteria.map((c) => {
      if (!Array.isArray(c.where)) return c;
      const cleaned = c.where.filter((w) => {
        if (w.source === "curve_class") {
          return Array.isArray(w.curve_classes) && w.curve_classes.length > 0;
        }
        // Any-protocol potency rows are readout-def-less by design.
        if (!w.readout_definition_id && !(c.protocol_id === null && w.source === "dr_curve")) {
          return false;
        }
        if (w.operator === "between") {
          return w.min !== undefined && w.max !== undefined;
        }
        return w.value !== undefined && !Number.isNaN(w.value);
      });
      return { ...c, where: cleaned };
    });
    // Filter to valid criteria and their matching conjunctions
    const validIndices = cleanedActivity
      .map((c, i) => (c.protocol_id !== "" ? i : -1)) // null = any protocol, valid
      .filter((i) => i >= 0);
    const validActivity = validIndices.map((i) => cleanedActivity[i]);
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
      const subValue = structureCriterion.smiles_or_smarts ?? structureCriterion.smarts ?? "";
      const hasValue =
        (structureCriterion.search_type === "substructure" && subValue.length > 0) ||
        (structureCriterion.search_type === "similarity" &&
          structureCriterion.smiles &&
          structureCriterion.smiles.length > 0) ||
        (structureCriterion.search_type === "exact" &&
          structureCriterion.inchi_key &&
          structureCriterion.inchi_key.length > 0);
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

    // Tags
    for (const c of tagSectionToCriteria(tagValue)) {
      criteria.push(c);
    }

    // Scaffold — emitted as-is; exact_match rows without a smiles are skipped
    // so a half-filled row doesn't reach the BE as a 422.
    for (const c of scaffoldCriteria) {
      if (c.mode === "acyclic_only" || (c.mode === "exact_match" && c.scaffold_smiles)) {
        criteria.push(c);
      }
    }

    // Text / Keywords
    for (const c of textCriteria) {
      if (c.value) criteria.push(c);
    }

    // Advanced: selectivity
    for (const c of advanced.selectivity) {
      if (c.target_readout_definition_id && c.counter_readout_definition_id) criteria.push(c);
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
  }, [
    projectIds,
    activityCriteria,
    protocolConjunctions,
    structureCriterion,
    propertyCriteria,
    collectionTerms,
    scaffoldCriteria,
    tagValue,
    textCriteria,
    advanced,
  ]);

  function handleSearch() {
    const criteria = composeCriteria();
    const query: SearchQuery = { criteria, logic: "and" };
    const protocolColumns = deriveProtocolColumns(activityCriteria, protocols);
    onSearch(query, protocolColumns);
  }

  function handleReset() {
    setActivityCriteria([]);
    setProtocolConjunctions([]);
    setStructureCriterion(null);
    setPropertyCriteria([]);
    setCollectionTerms([]);
    setScaffoldCriteria([]);
    setTextCriteria([]);
    setAdvanced(emptyAdvancedFilters());
    setTagValue(defaultTagSectionValue());
    onProjectsChange([]);
  }

  // Compose once per render; both the filter-count display and the live
  // count preview key off the same composed query so they never drift.
  const composedCriteria = composeCriteria();
  const criteriaCount = composedCriteria.length;
  // biome-ignore lint/correctness/useExhaustiveDependencies: composedCriteria is rebuilt every render but its serialization is stable across no-op renders, so we key on JSON.stringify so consumers (useSearchCount) can debounce.
  const composedQuery: SearchQuery = useMemo(
    () => ({ criteria: composedCriteria, logic: "and" }),
    [JSON.stringify(composedCriteria)],
  );

  // Similarity searches return everything above the threshold; the panel only
  // shows the top-K ranked. Surface that distinction so the chemist knows the
  // raw count is bigger than what they see in the result list.
  // biome-ignore lint/correctness/useExhaustiveDependencies: keyed on the stable serialization of composedCriteria (rebuilt each render); see composedQuery above.
  const isSimilarityQuery = useMemo(
    () => containsSimilarity(composedCriteria),
    [JSON.stringify(composedCriteria)],
  );

  // Skip the count when there are no criteria — the badge is hidden in that
  // case and we don't want to fire a workspace-wide COUNT(*) on every render.
  const countQuery = useSearchCount(composedQuery, criteriaCount > 0);
  const totalCount = countQuery.data?.total_count;
  const countIsFetching = countQuery.isFetching;

  // ⌘/Ctrl+Enter from anywhere inside the form fires Search.
  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSearch();
    }
  }

  return (
    <div
      className="rounded-lg border border-border bg-card overflow-hidden"
      onKeyDown={handleKeyDown}
    >
      <div className="p-4 pb-2">
        {/* Header: projects only — Search/Reset moved to sticky bottom bar. */}
        <div className="flex items-center justify-between mb-3 pb-3 border-b border-border">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground flex-shrink-0">
              Projects
            </span>
            <ProjectFilter selectedIds={projectIds} onChange={onProjectsChange} />
          </div>
        </div>

        {/* Protocols — full width */}
        <ProtocolSection
          criteria={activityCriteria}
          conjunctions={protocolConjunctions}
          projectIds={projectIds}
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
          <CollectionSection
            terms={collectionTerms}
            projectIds={projectIds}
            onChange={setCollectionTerms}
          />
          <KeywordSection criteria={textCriteria} onChange={setTextCriteria} />
        </div>

        <Separator className="my-3" />

        {/* Tags */}
        <TagSection value={tagValue} onChange={setTagValue} />

        <Separator className="my-3" />

        {/* Scaffold filter section — always rendered so chemists can compose
            a query against Bemis-Murcko scaffolds directly. The scaffold-tree
            "find in search" action stashes a criterion in sessionStorage; the
            page reads it on mount, fires the search, and populates this
            section so the active filter is visible + editable. */}
        <ScaffoldSection criteria={scaffoldCriteria} onChange={setScaffoldCriteria} />

        {/* More Filters */}
        <div className="mt-3 pt-3 border-t border-border">
          <AdvancedFilters state={advanced} onChange={setAdvanced} />
        </div>
      </div>

      {/* Sticky bottom action bar — pinned within the search panel so it stays
          reachable as the form grows. ⌘/Ctrl+Enter also fires Search. */}
      <div className="sticky bottom-0 z-10 flex items-center justify-between gap-2 border-t border-border bg-card/95 px-4 py-2.5 backdrop-blur supports-[backdrop-filter]:bg-card/80">
        <Button
          variant="ghost"
          size="sm"
          onClick={handleReset}
          className="text-muted-foreground hover:text-foreground"
        >
          <RotateCcw className="h-3.5 w-3.5 mr-1.5" /> Reset
        </Button>
        <div className="flex items-center gap-3">
          {/* Forecast lives next to the action, not inside it. The button is
              an action affordance ("click to run"); the count is metadata
              about the composed query ("this many will come back"). Mixing
              the two reads as "Search [these N compounds]" -- the wrong
              semantic. We fall back to the raw filter count only when the
              live preview hasn't returned yet. */}
          {criteriaCount > 0 && (
            <span
              className={`text-xs text-muted-foreground transition-opacity ${
                countIsFetching ? "opacity-60" : "opacity-100"
              }`}
              aria-live="polite"
            >
              {totalCount !== undefined ? (
                <>
                  <span
                    className={`tabular-nums ${
                      totalCount === 0
                        ? "font-medium text-amber-600 dark:text-amber-500"
                        : "text-foreground/80"
                    }`}
                  >
                    {totalCount.toLocaleString()}
                  </span>{" "}
                  compound{totalCount === 1 ? "" : "s"} match
                  {isSimilarityQuery && (
                    <span className="ml-1.5 text-muted-foreground/70">· ranked, top 50 shown</span>
                  )}
                </>
              ) : (
                <>
                  {criteriaCount} filter{criteriaCount === 1 ? "" : "s"}
                </>
              )}
            </span>
          )}
          <span className="hidden text-[10px] uppercase tracking-wider text-muted-foreground/60 sm:inline">
            ⌘ ↵
          </span>
          <Button onClick={handleSearch} disabled={isLoading} className="px-5">
            <Search className="h-4 w-4 mr-2" />
            Search
          </Button>
        </div>
      </div>
    </div>
  );
}
