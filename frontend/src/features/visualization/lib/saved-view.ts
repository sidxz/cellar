import type { PanelConfig } from "../store/workbench-store";
import type { Dataset } from "../types";
import { VIEW_CONFIG_VERSION, type ViewConfig, viewConfigSchema } from "./config-schema";
import { column } from "./dataset";
import type { Filter } from "./filters";
import { carryConfig } from "./level-switch";

type SavedFilter = ViewConfig["filters"][number];

/** The column keys a panel reads. */
const panelKeys = (p: PanelConfig) => {
  const a = p.appearance;
  return [p.x, p.y, p.category, a.colorBy, a.shapeBy, a.sizeBy, a.splitBy, ...a.tooltip];
};

/** What a saved view stores of the workbench: its plots and its range and category filters
 * ("Filter to selection" names rows of this dataset, so it stays behind), with the label of
 * every column they reference. */
export function buildViewConfig(
  state: { panels: PanelConfig[]; filters: Filter[] },
  ds: Dataset,
): ViewConfig {
  const filters = state.filters.filter((f): f is SavedFilter => f.kind !== "rows");
  const labels: Record<string, string> = {};
  for (const key of [...state.panels.flatMap(panelKeys), ...filters.map((f) => f.key)]) {
    const label = key === undefined ? undefined : column(ds, key)?.label;
    if (key !== undefined && label !== undefined) labels[key] = label;
  }
  return { config_version: VIEW_CONFIG_VERSION, panels: state.panels, filters, labels };
}

/** The config's size as stored: UTF-8 bytes of its compact JSON. */
export const configBytes = (cfg: ViewConfig) =>
  new TextEncoder().encode(JSON.stringify(cfg)).length;

/** ``MIGRATIONS[v]`` turns a version-``v`` config into a version-``v + 1`` one. */
// biome-ignore lint/suspicious/noExplicitAny: a step reads a config of an older shape
export const MIGRATIONS: Record<number, (c: any) => any> = {};

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
