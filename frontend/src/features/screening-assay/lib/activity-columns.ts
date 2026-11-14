/** Which columns a protocol's Activity grid has, how they are grouped and
 *  headed, and which show by default. Pure; the grid builds from it.
 *
 *  A chemist scans a few endpoints per compound, so each readout is ONE column
 *  (the table-wide Best/Mean switch picks the statistic), a thermal-shift
 *  window's readouts share one header, and only what a chemist compares on
 *  shows by default: the series values of each window, a dose-response's
 *  primary intercept, class and curve, anything the hit rule uses. Raw
 *  instrument values, absolute Tm, secondary intercepts and readouts with no
 *  results are one click away in the Columns menu. */

import type { CompoundActivity, HitCriterion, InterceptSpec, ReadoutDefInfo } from "../types";
import { interceptLabel } from "./intercept-label";

export type ColumnKind = "value" | "intercept" | "class" | "curve";

export interface CatalogColumn {
  colId: string;
  /** The readout the column reads. */
  readout: string;
  kind: ColumnKind;
  /** Short header, unit included. */
  label: string;
  /** Group header; null for an ungrouped column. */
  group: string | null;
  defaultVisible: boolean;
  /** No compound has a value. */
  empty: boolean;
  intercept?: InterceptSpec;
  primary?: boolean;
}

export interface ColumnChoices {
  shown: readonly string[];
  hidden: readonly string[];
}

const SERIES = ["max_delta_tm", "lowest_shift_concentration", "delta_tm_at_concentration"];
// Within a window: series values first, then the per-position values.
const MELT_ORDER = [...SERIES, "delta_tm", "tm"];
const OTHER = "Other readouts";

const withUnit = (label: string, unit: string | null | undefined) =>
  unit ? `${label} (${unit})` : label;

function meltLabel(rd: ReadoutDefInfo): string {
  const mc = rd.melt_config;
  switch (mc?.measure) {
    case "tm":
      return withUnit("Tm", rd.unit);
    case "delta_tm":
      return withUnit("ΔTm", rd.unit);
    case "max_delta_tm":
      return withUnit("Max ΔTm", rd.unit);
    case "lowest_shift_concentration":
      return withUnit(`Lowest shift ±${mc.threshold} °C`, rd.unit);
    default: {
      // ΔTm at a stated concentration: its name carries the concentration.
      const name = rd.name.replace(/\s*\([^()]*\)\s*$/, "");
      return withUnit(name, rd.unit);
    }
  }
}

const windowHeader = (rd: ReadoutDefInfo) => {
  const mc = rd.melt_config;
  return mc ? `${mc.window} window · ${mc.low}–${mc.high} °C` : "";
};

export function activityCatalog(
  readoutDefs: readonly ReadoutDefInfo[],
  items: readonly CompoundActivity[],
  criteria: readonly HitCriterion[],
): CatalogColumn[] {
  const inRule = new Set(criteria.map((c) => c.readout_name));
  const hasValue = (name: string) => items.some((i) => i.readouts?.[name]?.best != null);
  const thermal = readoutDefs.some((rd) => rd.melt_config);
  const windowHasSeries = (window: string) =>
    readoutDefs.some(
      (rd) =>
        rd.melt_config?.window === window &&
        SERIES.includes(rd.melt_config.measure) &&
        hasValue(rd.name),
    );

  // Groups in order of first appearance; a window's columns in MELT_ORDER.
  const groups = new Map<string, CatalogColumn[]>();
  const add = (key: string, col: CatalogColumn) =>
    groups.set(key, [...(groups.get(key) ?? []), col]);

  for (const rd of readoutDefs) {
    const empty = !hasValue(rd.name);
    const shownIf = (byDefault: boolean) => inRule.has(rd.name) || (!empty && byDefault);

    if (rd.data_type === "dose_response") {
      const specs = rd.intercepts ?? [];
      const unit = rd.unit;
      if (specs.length === 0) {
        add(`dr:${rd.name}`, {
          colId: `${rd.name}::best`,
          readout: rd.name,
          kind: "intercept",
          label: withUnit("Best", unit),
          group: rd.name,
          defaultVisible: shownIf(true),
          empty,
          primary: true,
        });
      }
      specs.forEach((spec, i) =>
        add(`dr:${rd.name}`, {
          colId: `${rd.name}::${spec.kind}${spec.level}`,
          readout: rd.name,
          kind: "intercept",
          label: withUnit(interceptLabel(spec), unit),
          group: rd.name,
          defaultVisible: shownIf(i === 0),
          empty,
          intercept: spec,
          primary: i === 0,
        }),
      );
      for (const kind of ["class", "curve"] as const) {
        add(`dr:${rd.name}`, {
          colId: `${rd.name}::${kind}`,
          readout: rd.name,
          kind,
          label: kind === "class" ? "Class" : "Curve",
          group: rd.name,
          defaultVisible: shownIf(true),
          empty,
        });
      }
      continue;
    }

    const mc = rd.melt_config;
    if (mc) {
      const byDefault = SERIES.includes(mc.measure)
        ? true
        : mc.measure === "delta_tm" && !windowHasSeries(mc.window);
      add(`melt:${mc.window}`, {
        colId: `${rd.name}::value`,
        readout: rd.name,
        kind: "value",
        label: meltLabel(rd),
        group: windowHeader(rd),
        defaultVisible: shownIf(byDefault),
        empty,
      });
      continue;
    }

    // A plain readout: on demand beside thermal-shift windows (raw instrument
    // values), shown ungrouped otherwise (a single-point assay's result).
    add(thermal ? "other" : `plain:${rd.name}`, {
      colId: `${rd.name}::value`,
      readout: rd.name,
      kind: "value",
      label: withUnit(rd.name, rd.unit),
      group: thermal ? OTHER : null,
      defaultVisible: shownIf(!thermal),
      empty,
    });
  }

  const measureRank = (c: CatalogColumn) =>
    MELT_ORDER.indexOf(readoutDefs.find((rd) => rd.name === c.readout)?.melt_config?.measure ?? "");
  const out: CatalogColumn[] = [];
  // Windows first (they are the results), then everything else in protocol order.
  const keys = [...groups.keys()];
  for (const key of [
    ...keys.filter((k) => k.startsWith("melt:")),
    ...keys.filter((k) => !k.startsWith("melt:")),
  ]) {
    const cols = groups.get(key) as CatalogColumn[];
    out.push(
      ...(key.startsWith("melt:")
        ? [...cols].sort((a, b) => measureRank(a) - measureRank(b))
        : cols),
    );
  }
  return out;
}

/** The defaults with the user's Columns-menu choices applied. */
export function visibleColumnIds(
  catalog: readonly CatalogColumn[],
  choices: ColumnChoices,
): Set<string> {
  const shown = new Set(choices.shown);
  const hidden = new Set(choices.hidden);
  return new Set(
    catalog
      .filter((c) => (c.defaultVisible || shown.has(c.colId)) && !hidden.has(c.colId))
      .map((c) => c.colId),
  );
}

type Direction = ReadoutDefInfo["best_direction"];

/** An AG Grid comparator that puts missing values last in either sort order
 *  and, for a shift, compares size in either direction. */
export function compareForDirection(direction: Direction) {
  return (a: unknown, b: unknown, _nodeA?: unknown, _nodeB?: unknown, isDescending = false) => {
    const x = typeof a === "number" ? a : null;
    const y = typeof b === "number" ? b : null;
    if (x == null && y == null) return 0;
    // Missing sorts last whichever way the column is sorted.
    if (x == null) return isDescending ? -1 : 1;
    if (y == null) return isDescending ? 1 : -1;
    return direction === "magnitude" ? Math.abs(x) - Math.abs(y) : x - y;
  };
}

/** The column the grid sorts by at first: the hit rule's readout, else the
 *  first value shown; best first in the readout's direction. */
export function defaultSortColumn(
  catalog: readonly CatalogColumn[],
  readoutDefs: readonly ReadoutDefInfo[],
  criteria: readonly HitCriterion[],
): { colId: string; sort: "asc" | "desc" } | null {
  const sortable = catalog.filter(
    (c) => c.defaultVisible && (c.kind === "value" || (c.kind === "intercept" && c.primary)),
  );
  const ruled = new Set(criteria.map((c) => c.readout_name));
  const pick = sortable.find((c) => ruled.has(c.readout)) ?? sortable[0];
  if (!pick) return null;
  const rd = readoutDefs.find((r) => r.name === pick.readout);
  return { colId: pick.colId, sort: rd?.best_direction === "low" ? "asc" : "desc" };
}
