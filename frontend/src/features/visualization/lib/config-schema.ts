import { z } from "zod";

/** The single definition of the workbench's plot and filter settings: the store's types are
 * inferred from these, and a saved view's config is checked against them on load. */

export const VIEW_CONFIG_VERSION = 1;
export const MAX_VIEW_CONFIG_BYTES = 65_536;
export const MAX_PANELS = 4;

export const appearanceSchema = z.object({
  colorBy: z.string().optional(),
  colorMode: z.enum(["range", "bins"]),
  colorBins: z.array(z.number()).optional(),
  shapeBy: z.string().optional(),
  sizeBy: z.string().optional(),
  opacity: z.number(),
  splitBy: z.string().optional(),
  tooltip: z.array(z.string()),
  showFiltered: z.boolean(),
});

/** Display-only marks drawn over a plot. */
export const overlaySchema = z.object({
  bands: z.boolean().optional(),
  drift: z.enum(["band", "trend"]).optional(),
  zPrime: z.boolean().optional(),
  refLine: z.number().optional(),
  limits: z
    .discriminatedUnion("mode", [
      z.object({ mode: z.literal("plotted") }),
      z.object({ mode: z.literal("entered"), lower: z.number(), upper: z.number() }),
    ])
    .optional(),
  lipe: z.array(z.number()).optional(),
  selectivity: z.array(z.number()).optional(),
});

export const panelSchema = z.object({
  id: z.string(),
  type: z.enum(["scatter", "histogram", "bar", "box"]),
  x: z.string().optional(),
  y: z.string().optional(),
  category: z.string().optional(),
  agg: z.enum(["count", "mean", "median"]).optional(),
  logX: z.boolean().optional(),
  logY: z.boolean().optional(),
  bins: z.number().optional(),
  appearance: appearanceSchema,
  overlays: overlaySchema.optional(),
});

const rangeFilter = z.object({
  id: z.string(),
  kind: z.literal("range"),
  key: z.string(),
  min: z.number().nullable(),
  max: z.number().nullable(),
  includeMissing: z.boolean(),
});

const categoryFilter = z.object({
  id: z.string(),
  kind: z.literal("category"),
  key: z.string(),
  values: z.array(z.string()),
  includeMissing: z.boolean(),
});

/** "Filter to selection": row ids of one dataset, so never saved. */
const rowsFilter = z.object({
  id: z.string(),
  kind: z.literal("rows"),
  rowIds: z.array(z.string()),
});

/** Rows whose compound contains a structure: ``moleculeIds`` are the dataset compounds the
 * query matched. Matches are data, so never saved; molecule ids are the same at every
 * level, so a level switch keeps it. */
const substructureFilter = z.object({
  id: z.string(),
  kind: z.literal("substructure"),
  query: z.string(),
  queryKind: z.enum(["smiles", "smarts"]),
  moleculeIds: z.array(z.string()),
});

export const filterSchema = z.discriminatedUnion("kind", [
  rangeFilter,
  categoryFilter,
  rowsFilter,
  substructureFilter,
]);
export const savedFilterSchema = z.discriminatedUnion("kind", [rangeFilter, categoryFilter]);

/** How a saved view looks — never its data. ``labels`` names each referenced column key, so
 * what no longer resolves can be listed by name. */
export const viewConfigSchema = z.object({
  config_version: z.number().int(),
  panels: z.array(panelSchema).max(MAX_PANELS),
  filters: z.array(savedFilterSchema).max(100),
  labels: z.record(z.string(), z.string()),
});

export type ViewConfig = z.infer<typeof viewConfigSchema>;
