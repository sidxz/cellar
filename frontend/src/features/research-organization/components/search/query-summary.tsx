"use client";

import type { Protocol } from "@/features/screening-assay/types";
import {
  buildActivityWhereOptions,
  whereConditionOptionId,
} from "../../lib/activity-where-options";
import type {
  ActivityWhereCondition,
  ColumnSplitWire,
  RunScope,
  SearchCriterion,
  SearchQuery,
  StructureCriterion,
} from "../../types";

export interface SummaryContext {
  protocols?: Protocol[];
  projects?: { id: string; name: string }[];
  collections?: { id: string; name: string }[];
  tags?: { id: string; name: string }[];
}

const FIELDS: Record<string, string> = {
  molecular_weight: "MW",
  logp: "LogP",
  tpsa: "TPSA",
  hbd: "HBD",
  hba: "HBA",
  rotatable_bonds: "Rotatable bonds",
  heavy_atom_count: "Heavy atoms",
  aromatic_rings: "Aromatic rings",
  ring_count: "Rings",
  ro5_violations: "Ro5 violations",
  registration_number: "Compound ID",
  molecular_formula: "Formula",
  inchi_key: "InChIKey",
  any: "Any field",
  name: "Name",
};
const OPS: Record<string, string> = {
  eq: "=",
  lt: "<",
  lte: "≤",
  gt: ">",
  gte: "≥",
  equals: "=",
  contains: "contains",
  starts_with: "starts with",
};
const fieldName = (field: string) => FIELDS[field] ?? field.replaceAll("_", " ");
const named = (items: { id: string; name: string }[] | undefined, id: string, kind: string) =>
  items?.find((item) => item.id === id)?.name ?? `${kind} ${id}`;

function bounds(
  c: { operator?: string; value?: string | number; min?: number; max?: number },
  unit?: string | null,
): string {
  const suffix = unit ? ` ${unit}` : "";
  if (c.operator === "between") {
    if (c.min != null && c.max != null) return `${c.min}–${c.max}${suffix}`;
    if (c.min != null) return `≥ ${c.min}${suffix}`;
    if (c.max != null) return `≤ ${c.max}${suffix}`;
    return "any value";
  }
  return `${OPS[c.operator ?? "eq"] ?? c.operator} ${c.value ?? "…"}${suffix}`;
}

function splitText(split?: ColumnSplitWire): string {
  if (split?.by === "run") return ", split by run";
  if (split?.by === "condition" && split.condition) return `, split by ${split.condition}`;
  return "";
}

function runScopeText(scope?: RunScope): string {
  switch (scope?.mode) {
    case "latest":
      return "latest run";
    case "all":
      return "every run";
    case "specific":
      return `${scope.run_ids?.length ?? (scope.run_id ? 1 : 0)} selected run(s)`;
    case "date_range":
      return `runs ${scope.date_from ?? "any start date"} to ${scope.date_to ?? "today"}`;
    case "past_n_days":
      return `runs in the past ${scope.days} days`;
    default:
      return "any run";
  }
}

function activityCondition(c: ActivityWhereCondition, protocol?: Protocol): string {
  if (c.source === "curve_class") return `curve class is ${(c.curve_classes ?? []).join(" or ")}`;
  const option = buildActivityWhereOptions(protocol).find(
    (o) => o.id === whereConditionOptionId(c),
  );
  const endpoint = c.intercept_key
    ? `${c.intercept_key.kind.toUpperCase()}${c.intercept_key.level}`
    : "Potency";
  const label = option?.label ?? c.readout_name ?? endpoint;
  const unit = option
    ? option.unit
    : c.source === "dr_curve" && !c.readout_definition_id
      ? "µM"
      : c.unit;
  return `${label} ${bounds(c, unit)}`;
}

function criterionText(c: SearchCriterion, context: SummaryContext): string {
  let text: string;
  switch (c.type) {
    case "group":
      text = `(${c.criteria.map((child) => criterionText(child, context)).join(c.logic === "or" ? " OR " : " AND ")})`;
      break;
    case "project":
      text = c.project_ids.length
        ? `Project: ${c.project_ids.map((id) => named(context.projects, id, "project")).join(" or ")}`
        : "All projects";
      break;
    case "text":
      text = `${fieldName(c.field)} ${OPS[c.operator]} “${c.value}”`;
      break;
    case "property":
      text = `${fieldName(c.field)} ${bounds(c)}`;
      break;
    case "structure":
      text =
        c.search_type === "similarity"
          ? `${c.mode === "scaffold_hop" ? "Scaffold hop" : c.mode === "fragment_in_target" ? "Contains my fragment" : "Similarity"} ≥ ${Math.round((c.threshold ?? 0.7) * 100)}%`
          : c.search_type === "exact"
            ? "Exact structure"
            : `Substructure match${c.generalized ? " (including tautomers and variants)" : ""}`;
      break;
    case "activity": {
      const protocol = context.protocols?.find((p) => p.id === c.protocol_id);
      const name =
        c.protocol_id === null ? "any assay" : (protocol?.name ?? `assay ${c.protocol_id}`);
      const conditions = c.where?.length
        ? c.where
        : c.operator && c.value != null
          ? [
              {
                source: c.source ?? "dr_curve",
                readout_definition_id: c.readout_definition_id ?? "",
                operator: c.operator,
                value: c.value,
              },
            ]
          : [];
      text = `Tested in ${name} (${runScopeText(c.run_scope)}${splitText(c.split)})${conditions.length ? ` where ${conditions.map((w) => activityCondition(w, protocol)).join(" AND ")}` : ""}`;
      if (conditions.length > 1) text = `(${text})`;
      break;
    }
    case "collection":
      text = `In ${named(context.collections, c.collection_id, "collection")}`;
      break;
    case "tag":
      text = `Tags: ${c.tag_ids.map((id) => named(context.tags, id, "tag")).join(c.tag_logic === "all" ? " AND " : " OR ")}`;
      if (c.tag_ids.length > 1) text = `(${text})`;
      break;
    case "scaffold":
      text =
        c.mode === "acyclic_only"
          ? "Acyclic compounds"
          : c.mode === "exact_match_in"
            ? `One of ${c.scaffold_smiles_list?.length ?? 0} scaffolds`
            : `Scaffold: ${c.scaffold_smiles}`;
      break;
    case "keyword_list":
      text = `${c.values.length} identifiers (${c.ref_type})`;
      break;
    case "run_date":
      text = `Run date: ${c.date_from ?? "any start date"} to ${c.date_to ?? "today"}`;
      break;
    case "batch":
      text = `Batch ${fieldName(c.field ?? "date")}: ${c.field_type === "date" ? `${c.date_from ?? "any start date"} to ${c.date_to ?? "today"}` : bounds(c)}`;
      break;
    case "custom_field":
      text = `${c.field} ${bounds(c)}`;
      break;
    case "selectivity": {
      const readouts = context.protocols?.flatMap((p) =>
        p.readout_definitions.map((r) => ({ id: r.id, name: `${p.name} / ${r.name}` })),
      );
      text = `Selectivity (${named(readouts, c.counter_readout_definition_id, "counter readout")} / ${named(readouts, c.target_readout_definition_id, "target readout")}) ${bounds({ operator: c.ratio_operator, value: c.ratio_value })}-fold`;
      break;
    }
  }
  return c.negate ? `NOT (${text})` : text;
}

export function querySummaryText(
  query: SearchQuery | Record<string, unknown>,
  context: SummaryContext = {},
): string {
  const criteria = query.criteria as SearchCriterion[] | undefined;
  if (!criteria?.length) return "All compounds · All projects";
  const hasProject = (items: SearchCriterion[]): boolean =>
    items.some((c) => c.type === "project" || (c.type === "group" && hasProject(c.criteria)));
  const scope = hasProject(criteria) ? "" : "All projects · ";
  return (
    scope +
    criteria.map((c) => criterionText(c, context)).join(query.logic === "or" ? " OR " : " AND ")
  );
}

/** Stable across object-key order and equivalent AND/OR criterion ordering. */
export function searchQueryKey(query: SearchQuery): string {
  function canonical(value: unknown, key?: string): unknown {
    if (Array.isArray(value)) {
      const items = value.map((item) => canonical(item));
      return key === "criteria"
        ? items.sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)))
        : items;
    }
    if (value && typeof value === "object") {
      return Object.fromEntries(
        Object.entries(value)
          .filter(([, v]) => v !== undefined)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([k, v]) => [k, canonical(v, k)]),
      );
    }
    return value;
  }
  return JSON.stringify(canonical({ ...query, logic: query.logic ?? "and" }));
}

export function structureQuery(query: SearchQuery | null): StructureCriterion | undefined {
  // Only a positive top-level criterion applies to every returned compound.
  return query?.criteria.find((c): c is StructureCriterion => c.type === "structure" && !c.negate);
}

export function QuerySummary({
  query,
  context,
  className,
}: { query: SearchQuery | Record<string, unknown>; context?: SummaryContext; className?: string }) {
  const summary = querySummaryText(query, context);
  return (
    <span className={className ?? "text-xs text-muted-foreground truncate"} title={summary}>
      {summary}
    </span>
  );
}
