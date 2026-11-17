import { z } from "zod";
import type { PanelConfig } from "../store/workbench-store";
import type { Dataset } from "../types";
import {
  MAX_VIEW_CONFIG_BYTES,
  VIEW_CONFIG_VERSION,
  type ViewConfig,
  derivedSpecSchema,
  viewConfigSchema,
} from "./config-schema";
import { column } from "./dataset";
import type { DerivedSpec } from "./derived";
import type { Filter } from "./filters";
import { carryConfig } from "./level-switch";

type SavedFilter = ViewConfig["filters"][number];

/** The column keys a panel reads. */
const panelKeys = (p: PanelConfig) => {
  const a = p.appearance;
  return [p.x, p.y, p.category, a.colorBy, a.shapeBy, a.sizeBy, a.splitBy, ...a.tooltip];
};

type Settings = { panels: PanelConfig[]; filters: Filter[] };

/** The filters a view stores: "Filter to selection" names rows of this dataset, so it stays
 * behind, and a substructure filter keeps its query without the compounds it matched. */
function savedFilters(filters: Filter[]): SavedFilter[] {
  return filters.flatMap((f): SavedFilter[] => {
    if (f.kind === "rows") return [];
    if (f.kind === "substructure") {
      return [{ id: f.id, kind: f.kind, query: f.query, queryKind: f.queryKind }];
    }
    return [f];
  });
}

/** What a saved view stores of the workbench: its plots and its saved filters, with the
 * label of every column they reference, and how its chemistry columns were computed. */
export function buildViewConfig(
  state: Settings,
  ds: Dataset,
  derived: DerivedSpec[] = [],
): ViewConfig {
  const filters = savedFilters(state.filters);
  const filterKeys = filters.map((f) => ("key" in f ? f.key : undefined));
  const labels: Record<string, string> = {};
  for (const key of [...state.panels.flatMap(panelKeys), ...filterKeys]) {
    const label = key === undefined ? undefined : column(ds, key)?.label;
    if (key !== undefined && label !== undefined) labels[key] = label;
  }
  return { config_version: VIEW_CONFIG_VERSION, panels: state.panels, filters, labels, derived };
}

/** Whether ``a`` and ``b`` save as the same view (a selection or a query's matches never
 * tell them apart). */
export const sameSaved = (a: Settings, b: Settings) =>
  (a.panels === b.panels && a.filters === b.filters) ||
  JSON.stringify([a.panels, savedFilters(a.filters)]) ===
    JSON.stringify([b.panels, savedFilters(b.filters)]);

/** Whether two lists of chemistry column specs save the same (key order aside). */
export const sameDerived = (a: DerivedSpec[], b: DerivedSpec[]) =>
  a.length === b.length &&
  JSON.stringify(z.array(derivedSpecSchema).parse(a)) ===
    JSON.stringify(z.array(derivedSpecSchema).parse(b));

/** The config's size as stored: UTF-8 bytes of its compact JSON. */
export const configBytes = (cfg: ViewConfig) =>
  new TextEncoder().encode(JSON.stringify(cfg)).length;

/** Why ``cfg`` can't be saved for its size (the server's limit), or null. */
export function tooLargeToSave(cfg: ViewConfig): string | null {
  const bytes = configBytes(cfg);
  if (bytes <= MAX_VIEW_CONFIG_BYTES) return null;
  const kb = (n: number) => Math.ceil(n / 1024);
  return `These settings are too large to save (${kb(bytes)} KB of ${kb(MAX_VIEW_CONFIG_BYTES)} KB). Remove some category filter values.`;
}

/** ``MIGRATIONS[v]`` turns a version-``v`` config into a version-``v + 1`` one. */
// biome-ignore lint/suspicious/noExplicitAny: a step reads a config of an older shape
export const MIGRATIONS: Record<number, (c: any) => any> = {
  // Version 2 saves how chemistry columns were computed.
  1: (c) => ({ ...c, config_version: 2, derived: [] }),
};

const UNREADABLE = "This view's settings can't be read.";
const NEWER = "This view was saved by a newer version of ChemCellar. Reload the page to open it.";

/** A stored config brought up to ``current`` one step at a time, then checked. */
export function migrateViewConfig(
  raw: unknown,
  current = VIEW_CONFIG_VERSION,
  // biome-ignore lint/suspicious/noExplicitAny: see MIGRATIONS
  steps: Record<number, (c: any) => any> = MIGRATIONS,
): { ok: true; config: ViewConfig } | { ok: false; reason: string } {
  const version = (raw as { config_version?: unknown } | null)?.config_version;
  if (typeof version !== "number" || !Number.isInteger(version)) {
    return { ok: false, reason: UNREADABLE };
  }
  if (version > current) return { ok: false, reason: NEWER };
  let cfg: unknown = raw;
  try {
    for (let v = version; v < current; v++) {
      const step = steps[v];
      if (!step) return { ok: false, reason: UNREADABLE };
      cfg = step(cfg);
    }
  } catch {
    return { ok: false, reason: UNREADABLE };
  }
  const parsed = viewConfigSchema.safeParse(cfg);
  return parsed.success ? { ok: true, config: parsed.data } : { ok: false, reason: UNREADABLE };
}

/** A saved config fitted to today's dataset; ``missing`` names, by saved label, each filter
 * and plot field whose column is gone. */
export function resolveViewConfig(
  cfg: ViewConfig,
  ds: Dataset,
): { panels: PanelConfig[]; filters: Filter[]; missing: string[] } {
  const { panels, filters, dropped } = carryConfig(
    { panels: cfg.panels, filters: cfg.filters, selectedIds: [], columns: [] },
    ds,
    cfg.labels,
  );
  return { panels, filters, missing: dropped };
}
