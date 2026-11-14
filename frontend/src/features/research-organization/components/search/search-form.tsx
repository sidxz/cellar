"use client";

import type { Protocol } from "@/features/screening-assay/types";
import { Button } from "@/shared/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import {
  ChevronDown,
  ChevronUp,
  Fingerprint,
  FlaskConical,
  Hexagon,
  Loader2,
  Plus,
  RotateCcw,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchCount } from "../../hooks/use-search-count";
import { ANY_COLUMN_ID, drcColId, rdColId } from "../../lib/protocol-column-id";
import type {
  ActivityCriterion,
  ActivityWhereCondition,
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
import { QuerySummary, type SummaryContext, searchQueryKey } from "./query-summary";
import { ScaffoldSection } from "./scaffold-section";
import { StructureSection } from "./structure-section";
import {
  TagSection,
  type TagSectionValue,
  defaultTagSectionValue,
  tagCriteriaToSection,
  tagSectionToCriteria,
} from "./tag-section";

/** Server-side page size for compound search results. Driven by what the
 * AG Grid viewport can comfortably render before the user scrolls; keep in
 * sync with the cursor pagination contract on the backend. */
export const SEARCH_PAGE_SIZE = 100;

// ─── Props ──────────────────────────────────────────────────────────────────

interface SearchFormProps {
  initialQuery?: SearchQuery;
  executedQuery?: SearchQuery | null;
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
  onDraftChange?: (query: SearchQuery) => void;
  summaryContext?: SummaryContext;
  /** Controls on the right of the header, before Collapse / Edit filters —
   *  in sight whether the filters are open or folded under the results. */
  headerActions?: React.ReactNode;
  projectIds: string[];
  onProjectsChange: (ids: string[]) => void;
  onSearch: (query: SearchQuery, protocolColumns: string[]) => void;
  /** Called after the form clears itself — the page drops its results. */
  onReset: () => void;
  isLoading?: boolean;
  /** Full protocol records (with readout_definitions) — used to pick sensible
   *  default columns when a criterion filters by protocol only. */
  protocols: Protocol[];
}

// ─── Helpers: decompose SearchQuery into section states ─────────────────────

export function decomposeQuery(query: SearchQuery | undefined) {
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
        // Top-level activity criteria are ANDed with what came before.
        protocolConjunctions.push("and");
        activityCriteria.push(c);
        break;
      case "group": {
        // A group joins the rows before it with AND (that's how
        // composeCriteria emits it); its members join each other with the
        // group's logic. Giving the first member the group logic too turned
        // "A and (B or C)" into "A or B or C" on the next compose.
        const group = c as GroupCriterion;
        let first = true;
        for (const gc of group.criteria) {
          if (gc.type === "activity") {
            protocolConjunctions.push(first ? "and" : group.logic);
            activityCriteria.push(gc as ActivityCriterion);
            first = false;
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
    if (c.protocol_id === null) {
      add(ANY_COLUMN_ID); // one "Active in" column for every any-protocol row
      continue;
    }
    if (!c.protocol_id) continue;
    const conds: Pick<
      ActivityWhereCondition,
      "source" | "readout_definition_id" | "normalization"
    >[] =
      Array.isArray(c.where) && c.where.length > 0
        ? c.where
        : c.readout_definition_id
          ? [{ source: c.source ?? "dr_curve", readout_definition_id: c.readout_definition_id }]
          : [];
    let addedAny = false;
    for (const cond of conds) {
      if (!cond.readout_definition_id) continue;
      if (cond.source === "readout_data") {
        // Show the layer that was filtered on (4-segment id = normalized view).
        const col = rdColId(c.protocol_id, cond.readout_definition_id);
        add(cond.normalization ? `${col}:${cond.normalization}` : col);
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

/** A numeric row is ready once it has something to compare against: a value,
 *  or for "between" at least one of min / max (open-ended ranges are valid —
 *  "MW ≤ 500" is the commonest med-chem filter). */
function hasNumericBound(c: {
  operator?: string;
  value?: unknown;
  min?: number;
  max?: number;
}): boolean {
  if (c.operator === "between") return c.min != null || c.max != null;
  return typeof c.value === "number" && !Number.isNaN(c.value);
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

type FilterSectionKey =
  | "assays"
  | "structure"
  | "identifiers"
  | "properties"
  | "collections"
  | "tags"
  | "scaffold"
  | "advanced";
const FILTER_SECTIONS: { key: FilterSectionKey; label: string }[] = [
  { key: "assays", label: "Assay activity" },
  { key: "structure", label: "Structure" },
  { key: "identifiers", label: "Compound identifiers" },
  { key: "properties", label: "Properties" },
  { key: "collections", label: "Collections" },
  { key: "tags", label: "Tags" },
  { key: "scaffold", label: "Scaffold" },
  { key: "advanced", label: "Advanced filters" },
];

export function countSearchCriteria(criteria: SearchCriterion[]): number {
  return criteria.reduce(
    (count, criterion) =>
      count + (criterion.type === "group" ? countSearchCriteria(criterion.criteria) : 1),
    0,
  );
}

function FilterCard({
  label,
  onRemove,
  children,
}: { label: string; onRemove: () => void; children: React.ReactNode }) {
  return (
    <section
      aria-label={label}
      className="relative rounded-xl border border-border/80 bg-background p-3 sm:p-4"
    >
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="absolute right-2 top-2 text-muted-foreground hover:text-destructive"
        aria-label={`Remove ${label.toLowerCase()} filters`}
        title={`Remove all ${label.toLowerCase()} filters`}
        onClick={onRemove}
      >
        <X className="size-3.5" />
      </Button>
      <div className="min-w-0 pr-6">{children}</div>
    </section>
  );
}

// ─── Component ──────────────────────────────────────────────────────────────

export function SearchForm({
  initialQuery,
  executedQuery,
  collapsed = false,
  onCollapsedChange,
  onDraftChange,
  summaryContext,
  headerActions,
  projectIds,
  onProjectsChange,
  onSearch,
  onReset,
  isLoading,
  protocols,
}: SearchFormProps) {
  // Parse initial query into section states
  const initial = decomposeQuery(initialQuery);
  const [openedSections, setOpenedSections] = useState<FilterSectionKey[]>([]);

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
    setOpenedSections([]);
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
    const cleanedActivity = activityCriteria.map(cleanActivityCriterion);
    // Filter to valid criteria and their matching conjunctions
    const validIndices = cleanedActivity
      .map((c, i) => (c.protocol_id === null || !!c.protocol_id ? i : -1)) // null = any protocol, valid
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
          !!(structureCriterion.inchi_key || structureCriterion.smiles));
      if (hasValue) criteria.push(structureCriterion);
    }

    // Properties — a row counts once it has a bound (Min, Max or both).
    for (const c of propertyCriteria) {
      if (hasNumericBound(c)) criteria.push(c);
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
      if (
        c.target_readout_definition_id &&
        c.counter_readout_definition_id &&
        c.ratio_value != null
      ) {
        criteria.push(c);
      }
    }

    // Advanced: batch — skip rows still waiting for a value
    for (const c of advanced.batch) {
      const ready =
        c.field_type === "date"
          ? !!(c.date_from || c.date_to)
          : c.field_type === "numeric"
            ? hasNumericBound(c)
            : typeof c.value === "string" && c.value.trim().length > 0;
      if (ready) criteria.push(c);
    }

    // Advanced: run date
    for (const c of advanced.runDate) {
      if (c.date_from || c.date_to) criteria.push(c);
    }

    // Advanced: custom fields
    for (const c of advanced.customFields) {
      const ready =
        c.mode === "numeric"
          ? hasNumericBound(c)
          : typeof c.value === "string" && c.value.trim().length > 0;
      if (c.field.trim() && ready) criteria.push(c);
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
    if (draftIssue) return;
    const criteria = composeCriteria();
    const query: SearchQuery = { criteria, logic: "and" };
    const protocolColumns = deriveProtocolColumns(activityCriteria, protocols);
    onSearch(query, protocolColumns);
  }

  function handleReset() {
    setOpenedSections([]);
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
    onReset();
  }

  // Compose once per render; both the filter-count display and the live
  // count preview key off the same composed query so they never drift.
  const composedCriteria = composeCriteria();
  const criteriaCount = countSearchCriteria(composedCriteria);
  const assayCount = activityCriteria.filter(
    (c) => c.protocol_id === null || !!c.protocol_id,
  ).length;
  const otherCount = criteriaCount - assayCount;
  const criteriaLabel =
    [
      assayCount > 0 ? `${assayCount} assay ${assayCount === 1 ? "criterion" : "criteria"}` : "",
      otherCount > 0
        ? `${otherCount} ${assayCount > 0 ? "other " : ""}filter${otherCount === 1 ? "" : "s"}`
        : "",
    ]
      .filter(Boolean)
      .join(" · ") || "All compounds";
  const visibleSections = new Set<FilterSectionKey>(openedSections);
  if (activityCriteria.length) visibleSections.add("assays");
  if (structureCriterion) visibleSections.add("structure");
  if (textCriteria.length) visibleSections.add("identifiers");
  if (propertyCriteria.length) visibleSections.add("properties");
  if (collectionTerms.length) visibleSections.add("collections");
  if (tagValue.tagIds.length) visibleSections.add("tags");
  if (scaffoldCriteria.length) visibleSections.add("scaffold");
  if (Object.values(advanced).some((terms) => terms.length > 0)) visibleSections.add("advanced");

  function addSection(key: FilterSectionKey) {
    setOpenedSections((sections) => [...new Set([...sections, key])]);
    if (key === "identifiers" && !textCriteria.length)
      setTextCriteria([
        { type: "text", field: "registration_number", operator: "contains", value: "" },
      ]);
    if (key === "properties" && !propertyCriteria.length)
      setPropertyCriteria([{ type: "property", field: "molecular_weight", operator: "between" }]);
    if (key === "collections" && !collectionTerms.length)
      setCollectionTerms([{ collection_id: "", negate: false }]);
    if (key === "scaffold" && !scaffoldCriteria.length)
      setScaffoldCriteria([{ type: "scaffold", mode: "exact_match", scaffold_smiles: "" }]);
  }
  function removeSection(key: FilterSectionKey) {
    setOpenedSections((sections) => sections.filter((section) => section !== key));
    if (key === "assays") {
      setActivityCriteria([]);
      setProtocolConjunctions([]);
    }
    if (key === "structure") setStructureCriterion(null);
    if (key === "identifiers") setTextCriteria([]);
    if (key === "properties") setPropertyCriteria([]);
    if (key === "collections") setCollectionTerms([]);
    if (key === "tags") setTagValue(defaultTagSectionValue());
    if (key === "scaffold") setScaffoldCriteria([]);
    if (key === "advanced") setAdvanced(emptyAdvancedFilters());
  }
  // biome-ignore lint/correctness/useExhaustiveDependencies: composedCriteria is rebuilt every render but its serialization is stable across no-op renders, so we key on JSON.stringify so consumers (useSearchCount) can debounce.
  const composedQuery: SearchQuery = useMemo(
    () => ({ criteria: composedCriteria, logic: "and" }),
    [JSON.stringify(composedCriteria)],
  );

  const filtersChanged =
    !!executedQuery && searchQueryKey(composedQuery) !== searchQueryKey(executedQuery);
  const filterToggleRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (collapsed) filterToggleRef.current?.focus({ preventScroll: true });
  }, [collapsed]);
  useEffect(() => {
    onDraftChange?.(composedQuery);
  }, [composedQuery, onDraftChange]);

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
  // A half-made choice the backend would reject: hold the count and Search
  // and say what's missing, instead of surfacing the backend's 422 text.
  const unpickedAssay = activityCriteria.findIndex(hasUnpickedRuns);
  const draftIssue =
    unpickedAssay >= 0 ? `Pick at least one run for assay ${unpickedAssay + 1}` : null;
  const countQuery = useSearchCount(composedQuery, criteriaCount > 0 && !draftIssue);
  const totalCount = countQuery.data?.total_count;
  const countIsFetching = countQuery.isFetching;
  // A 422 from the count (bad SMILES, unknown field…) is the earliest place
  // the chemist can learn the query is wrong — show it instead of a stale
  // number. ApiError.message reads "API error: 422 — <detail>".
  const countError =
    !countQuery.isDebouncing && countQuery.error instanceof Error
      ? countQuery.error.message.replace(/^API error: \d+ — /, "")
      : null;

  // ⌘/Ctrl+Enter fires Search from anywhere on the page. Listening on the
  // form div alone missed the commonest flow — pick a protocol, then ⌘↵ —
  // because closing a picker popover leaves focus on <body>. Dialogs
  // (structure editor, save search) keep the shortcut to themselves.
  const handleSearchRef = useRef(handleSearch);
  handleSearchRef.current = handleSearch;
  const isLoadingRef = useRef(isLoading);
  isLoadingRef.current = isLoading;
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Enter" || !(e.metaKey || e.ctrlKey)) return;
      // Held keys auto-repeat; the Search button is disabled while one runs.
      if (e.repeat || isLoadingRef.current) return;
      if (e.target instanceof Element && e.target.closest('[role="dialog"]')) return;
      e.preventDefault();
      handleSearchRef.current();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
          <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold">Search filters</h2>
          <span className="text-xs text-muted-foreground">
            {executedQuery && !filtersChanged ? "Applied · " : "Draft · "}
            {criteriaLabel}
          </span>
          {filtersChanged && (
            <output className="text-xs font-medium text-amber-700 dark:text-amber-400">
              Changes not applied
            </output>
          )}
        </div>
        <div className="flex items-center gap-1">
          {headerActions}
          {executedQuery && (
            <Button
              ref={filterToggleRef}
              variant="ghost"
              size="sm"
              aria-expanded={!collapsed}
              aria-controls="search-filter-fields"
              onClick={() => onCollapsedChange?.(!collapsed)}
            >
              {collapsed ? (
                <ChevronDown className="mr-1.5 h-4 w-4" />
              ) : (
                <ChevronUp className="mr-1.5 h-4 w-4" />
              )}
              {collapsed ? "Edit filters" : "Collapse filters"}
            </Button>
          )}
        </div>
      </div>
      <div id="search-filter-fields" hidden={collapsed}>
        <div className="space-y-4 border-t p-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium text-muted-foreground">Searching:</span>
            <ProjectFilter selectedIds={projectIds} onChange={onProjectsChange} />
          </div>

          {visibleSections.size === 0 && (
            <div className="space-y-3">
              <div>
                <h3 className="text-base font-semibold">What would you like to find?</h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  Start with a question, then combine filters to narrow your results.
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                {(
                  [
                    {
                      key: "assays",
                      label: "Assay activity",
                      description: "Find tested compounds and set activity thresholds",
                      Icon: FlaskConical,
                    },
                    {
                      key: "structure",
                      label: "Structure",
                      description: "Find a substructure, similar molecules, or an exact match",
                      Icon: Hexagon,
                    },
                    {
                      key: "identifiers",
                      label: "Compound identifiers",
                      description: "Look up compound IDs, names, formulas, or InChIKeys",
                      Icon: Fingerprint,
                    },
                  ] as const
                ).map(({ key, label, description, Icon }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => addSection(key)}
                    className="flex items-start gap-3 rounded-xl border border-border bg-background p-4 text-left transition-colors hover:border-primary/40 hover:bg-primary/5 focus-visible:outline-2 focus-visible:outline-primary"
                  >
                    <Icon className="mt-0.5 size-5 shrink-0 text-primary" />
                    <span>
                      <span className="block text-sm font-semibold">{label}</span>
                      <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">
                        {description}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-3">
            {visibleSections.has("assays") && (
              <FilterCard label="Assay activity" onRemove={() => removeSection("assays")}>
                <ProtocolSection
                  criteria={activityCriteria}
                  conjunctions={protocolConjunctions}
                  projectIds={projectIds}
                  protocols={protocols}
                  onChange={(criteria, conjs) => {
                    setActivityCriteria(criteria);
                    setProtocolConjunctions(conjs);
                  }}
                />
              </FilterCard>
            )}
            {visibleSections.has("structure") && (
              <FilterCard label="Structure" onRemove={() => removeSection("structure")}>
                <StructureSection criterion={structureCriterion} onChange={setStructureCriterion} />
              </FilterCard>
            )}
            {visibleSections.has("identifiers") && (
              <FilterCard
                label="Compound identifiers"
                onRemove={() => removeSection("identifiers")}
              >
                <KeywordSection criteria={textCriteria} onChange={setTextCriteria} />
              </FilterCard>
            )}
            {visibleSections.has("properties") && (
              <FilterCard label="Properties" onRemove={() => removeSection("properties")}>
                <PropertySection criteria={propertyCriteria} onChange={setPropertyCriteria} />
              </FilterCard>
            )}
            {visibleSections.has("collections") && (
              <FilterCard label="Collections" onRemove={() => removeSection("collections")}>
                <CollectionSection
                  terms={collectionTerms}
                  projectIds={projectIds}
                  onChange={setCollectionTerms}
                />
              </FilterCard>
            )}
            {visibleSections.has("tags") && (
              <FilterCard label="Tags" onRemove={() => removeSection("tags")}>
                <TagSection value={tagValue} onChange={setTagValue} />
              </FilterCard>
            )}
            {visibleSections.has("scaffold") && (
              <FilterCard label="Scaffold" onRemove={() => removeSection("scaffold")}>
                <ScaffoldSection criteria={scaffoldCriteria} onChange={setScaffoldCriteria} />
              </FilterCard>
            )}
            {visibleSections.has("advanced") && (
              <FilterCard label="Advanced" onRemove={() => removeSection("advanced")}>
                <AdvancedFilters state={advanced} onChange={setAdvanced} defaultOpen />
              </FilterCard>
            )}
          </div>
          {visibleSections.size < FILTER_SECTIONS.length && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button type="button" variant="outline" size="sm">
                  <Plus className="size-4" /> Add filter
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                {FILTER_SECTIONS.filter(({ key }) => !visibleSections.has(key)).map(
                  ({ key, label }) => (
                    <DropdownMenuItem key={key} onSelect={() => addSection(key)}>
                      {label}
                    </DropdownMenuItem>
                  ),
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          {visibleSections.size > 1 && (
            <p className="text-xs text-muted-foreground">
              Compounds must match all filter sections. Use the assay matching control to choose how
              assays are combined.
            </p>
          )}
        </div>
      </div>

      {/* Sticky bottom action bar — pinned within the search panel so it stays
          reachable as the form grows. ⌘/Ctrl+Enter also fires Search. */}
      {(!collapsed || filtersChanged) && (
        <div className="sticky bottom-0 z-10 rounded-b-xl border-t border-border bg-card/95 px-4 py-3 shadow-[0_-4px_16px_-12px_rgba(0,0,0,0.25)] backdrop-blur">
          {criteriaCount > 0 && (
            <div className="mb-2 line-clamp-2 text-xs text-muted-foreground">
              <span className="font-medium">
                {filtersChanged || !executedQuery ? "Draft search: " : "Search: "}
              </span>
              <QuerySummary
                query={composedQuery}
                context={summaryContext}
                className="leading-relaxed"
              />
            </div>
          )}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleReset}
              className="text-muted-foreground hover:text-foreground"
            >
              <RotateCcw className="h-3.5 w-3.5 mr-1.5" /> Reset
            </Button>
            <div className="flex flex-wrap items-center gap-3">
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
                  {draftIssue ? (
                    <span className="font-medium text-amber-700 dark:text-amber-400">
                      {draftIssue}
                    </span>
                  ) : countError ? (
                    <span className="font-medium text-destructive" title={countError}>
                      {countError}
                    </span>
                  ) : countQuery.isDebouncing || countIsFetching ? (
                    <span>Estimating matches…</span>
                  ) : totalCount !== undefined ? (
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
                      {isSimilarityQuery && totalCount > SEARCH_PAGE_SIZE && (
                        <span className="ml-1.5 text-muted-foreground/70">
                          · ranked, top {SEARCH_PAGE_SIZE} per page
                        </span>
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
              <Button onClick={handleSearch} disabled={isLoading || !!draftIssue} className="px-5">
                {isLoading ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Search className="h-4 w-4 mr-2" />
                )}
                {isLoading ? "Searching…" : filtersChanged ? "Update results" : "Search"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** "Specific runs" chosen on a protocol but no run picked yet — unfinished,
 *  and the backend rejects it. */
export function hasUnpickedRuns(c: ActivityCriterion): boolean {
  const scope = c.run_scope;
  return !!c.protocol_id && scope?.mode === "specific" && !scope.run_ids?.length && !scope.run_id;
}

/** An activity criterion as the backend should see it: half-filled where
 *  rows pruned (field missing, value missing for non-between, …) and a
 *  condition split with no condition chosen dropped. */
export function cleanActivityCriterion(c: ActivityCriterion): ActivityCriterion {
  const split = c.split?.by === "condition" && !c.split.condition ? undefined : c.split;
  if (!Array.isArray(c.where)) return { ...c, split };
  const cleaned = c.where.filter((w) => {
    if (w.source === "curve_class") {
      return Array.isArray(w.curve_classes) && w.curve_classes.length > 0;
    }
    // Any-protocol rows: potency (dr_curve, no rd) and readout-by-name are
    // readout-def-less by design.
    if (!w.readout_definition_id) {
      const anyDr = c.protocol_id === null && w.source === "dr_curve";
      const anyRd = c.protocol_id === null && w.source === "readout_data" && !!w.readout_name;
      if (!anyDr && !anyRd) return false;
    }
    if (w.operator === "between") {
      return w.min !== undefined && w.max !== undefined;
    }
    return w.value !== undefined && !Number.isNaN(w.value);
  });
  return { ...c, where: cleaned, split };
}
