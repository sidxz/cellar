/**
 * Map AG-Grid Community `filterModel` (text + number filters) and sort `colId`s
 * to the backend `/rows` `filter`/`sort` contract. Set filter is Enterprise, so
 * R-group columns use a Text filter. One `colIdToBackendKey` serves both sort and
 * filter so the column ids and the backend keys stay in sync in one place.
 */

export type FilterClause =
  | {
      kind: "number";
      op: "eq" | "neq" | "gt" | "gte" | "lt" | "lte" | "between";
      value: number;
      value2?: number;
    }
  | { kind: "text"; op: "contains" | "eq" | "startsWith" | "endsWith" | "neq"; value: string };

const COL_ID_TO_KEY: Record<string, string> = {
  registration_number: "registration_number",
  name: "name",
  mw: "molecular_weight",
  clogp: "logp",
  tpsa: "tpsa",
  "activity:value": "activity",
};

/** AG-Grid colId → backend filter/sort key, or null if not filterable/sortable. */
export function colIdToBackendKey(colId: string): string | null {
  if (colId in COL_ID_TO_KEY) return COL_ID_TO_KEY[colId];
  if (colId.startsWith("rg:")) return colId.slice(3); // "rg:R1" -> "R1"
  return null;
}

const TEXT_OPS: Record<string, FilterClause["op"]> = {
  contains: "contains",
  equals: "eq",
  notEqual: "neq",
  startsWith: "startsWith",
  endsWith: "endsWith",
};
const NUMBER_OPS: Record<string, "eq" | "neq" | "gt" | "gte" | "lt" | "lte"> = {
  equals: "eq",
  notEqual: "neq",
  greaterThan: "gt",
  greaterThanOrEqual: "gte",
  lessThan: "lt",
  lessThanOrEqual: "lte",
};

type AgFilter = { filterType?: string; type?: string; filter?: unknown; filterTo?: unknown };

export function agFilterModelToParam(
  filterModel: Record<string, AgFilter> | null | undefined,
): Record<string, FilterClause> | undefined {
  if (!filterModel) return undefined;
  const out: Record<string, FilterClause> = {};
  for (const [colId, model] of Object.entries(filterModel)) {
    const key = colIdToBackendKey(colId);
    if (!key || !model) continue;
    if (model.filterType === "text") {
      const op = model.type ? TEXT_OPS[model.type] : undefined;
      if (!op || model.filter == null) continue;
      out[key] = { kind: "text", op, value: String(model.filter) } as FilterClause;
    } else if (model.filterType === "number") {
      if (model.type === "inRange") {
        if (model.filter == null || model.filterTo == null) continue;
        out[key] = {
          kind: "number",
          op: "between",
          value: Number(model.filter),
          value2: Number(model.filterTo),
        };
      } else {
        const op = model.type ? NUMBER_OPS[model.type] : undefined;
        if (!op || model.filter == null) continue;
        out[key] = { kind: "number", op, value: Number(model.filter) };
      }
    }
  }
  return Object.keys(out).length ? out : undefined;
}
