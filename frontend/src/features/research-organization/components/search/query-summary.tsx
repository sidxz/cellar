"use client";

import type {
  ActivityCriterion,
  BatchCriterion,
  CustomFieldCriterion,
  GroupCriterion,
  KeywordListCriterion,
  ProjectCriterion,
  PropertyCriterion,
  PropertyOperator,
  RunDateCriterion,
  SearchCriterion,
  SelectivityCriterion,
  StructureCriterion,
  TextCriterion,
  TextOperator,
} from "../../types";

// ─── Helpers ─────────────────────────────────────────────────────────────────

const TEXT_OP_LABELS: Record<TextOperator, string> = {
  contains: "contains",
  equals: "=",
  starts_with: "starts with",
};

const PROP_OP_LABELS: Record<PropertyOperator, string> = {
  eq: "=",
  lt: "<",
  lte: "\u2264",
  gt: ">",
  gte: "\u2265",
  between: "\u2013",
};

function criterionText(c: SearchCriterion): string {
  const prefix = c.negate ? "NOT " : "";

  switch (c.type) {
    case "text": {
      const tc = c as TextCriterion;
      return `${prefix}${tc.field} ${TEXT_OP_LABELS[tc.operator]} "${tc.value}"`;
    }
    case "property": {
      const pc = c as PropertyCriterion;
      if (pc.operator === "between" && pc.min != null && pc.max != null) {
        return `${prefix}${pc.field}: ${pc.min}\u2013${pc.max}`;
      }
      return `${prefix}${pc.field} ${PROP_OP_LABELS[pc.operator]} ${pc.value ?? ""}`;
    }
    case "structure": {
      const sc = c as StructureCriterion;
      if (sc.search_type === "similarity") {
        const pct = sc.threshold != null ? Math.round(sc.threshold * 100) : 70;
        return `${prefix}Similarity \u2265 ${pct}%`;
      }
      if (sc.search_type === "exact") return `${prefix}Exact structure`;
      return `${prefix}Substructure match`;
    }
    case "activity": {
      const ac = c as ActivityCriterion;
      const where = Array.isArray(ac.where) && ac.where.length > 0 ? ac.where : null;
      if (where) {
        const n = where.length;
        return `${prefix}Protocol activity (${n} filter${n === 1 ? "" : "s"})`;
      }
      if (ac.operator !== undefined && ac.value !== undefined) {
        return `${prefix}Protocol activity ${PROP_OP_LABELS[ac.operator]} ${ac.value}`;
      }
      return `${prefix}Tested in protocol`;
    }
    case "collection": {
      return `${prefix}In collection`;
    }
    case "project": {
      const pc = c as ProjectCriterion;
      const n = pc.project_ids?.length ?? 0;
      return `${prefix}${n} project${n === 1 ? "" : "s"}`;
    }
    case "keyword_list": {
      const kc = c as KeywordListCriterion;
      const n = kc.values?.length ?? 0;
      return `${prefix}${n} identifier${n === 1 ? "" : "s"}`;
    }
    case "run_date": {
      const rc = c as RunDateCriterion;
      const from = rc.date_from ?? "...";
      const to = rc.date_to ?? "...";
      return `${prefix}Run date: ${from} \u2013 ${to}`;
    }
    case "batch": {
      const bc = c as BatchCriterion;
      return `${prefix}Batch: ${bc.field ?? "filter"}`;
    }
    case "selectivity": {
      const sc = c as SelectivityCriterion;
      return `${prefix}Selectivity ratio ${PROP_OP_LABELS[sc.ratio_operator]} ${sc.ratio_value}`;
    }
    case "custom_field": {
      const cf = c as CustomFieldCriterion;
      return `${prefix}Custom: ${cf.field}`;
    }
    case "group": {
      const gc = c as GroupCriterion;
      const n = gc.criteria?.length ?? 0;
      return `${prefix}(${n} grouped filter${n === 1 ? "" : "s"})`;
    }
    default:
      return `${prefix}${(c as { type: string }).type}`;
  }
}

// ─── Public API ──────────────────────────────────────────────────────────────

/**
 * Produces a human-readable text summary from a SearchQuery JSON object.
 * Handles both a full SearchQuery (`{ criteria, logic }`) and a bare object.
 */
export function querySummaryText(query: Record<string, unknown>): string {
  // Try to interpret as SearchQuery
  const criteria = query.criteria as SearchCriterion[] | undefined;
  if (!Array.isArray(criteria) || criteria.length === 0) {
    return "Empty query";
  }

  const logic = (query.logic as string) ?? "and";
  const separator = logic === "or" ? " OR " : " | ";

  return criteria.map(criterionText).join(separator);
}

// ─── Component ───────────────────────────────────────────────────────────────

interface QuerySummaryProps {
  query: Record<string, unknown>;
  className?: string;
}

export function QuerySummary({ query, className }: QuerySummaryProps) {
  return (
    <span
      className={className ?? "text-xs text-muted-foreground truncate"}
      title={querySummaryText(query)}
    >
      {querySummaryText(query)}
    </span>
  );
}
