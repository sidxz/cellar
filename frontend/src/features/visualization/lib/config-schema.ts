import { z } from "zod";

/** The single definition of the workbench's plot and filter settings: the store's types are
 * inferred from these, and a saved view's config is checked against them on load. */

export const VIEW_CONFIG_VERSION = 2;
export const MAX_VIEW_CONFIG_BYTES = 65_536;
export const MAX_PANELS = 4;

/** Each field defaults, so a stored plot's appearance reads whatever of it is there. */
export const appearanceSchema = z.object({
  colorBy: z.string().optional(),
  colorMode: z.enum(["range", "bins"]).default("range"),
  colorBins: z.array(z.number()).optional(),
  shapeBy: z.string().optional(),
  sizeBy: z.string().optional(),
  opacity: z.number().default(0.8),
  splitBy: z.string().optional(),
  tooltip: z.array(z.string()).default([]),
  showFiltered: z.boolean().default(true),
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
  // The backend accepts only these types when a view is saved: keep in step with ViewPanel.type
  // in backend/src/cellar/domain/research_organization/saved_visualization.py.
  type: z.enum(["scatter", "histogram", "bar", "box", "rgroup-matrix"]),
  x: z.string().optional(),
  y: z.string().optional(),
  category: z.string().optional(),
  agg: z.enum(["count", "mean", "median"]).optional(),
  logX: z.boolean().optional(),
  logY: z.boolean().optional(),
  bins: z.number().optional(),
  appearance: appearanceSchema.prefault({}),
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

/** Rows whose compound contains a structure: ``moleculeIds`` are the compounds the query
 * matched among ``over`` (``membershipKey`` of the dataset it was matched against). Absent,
 * or matched over other compounds than the open data's (runs added, a level that counts
 * other runs), it filters nothing until matched again. Matches are data, so a view saves
 * the query alone. */
const substructureFilter = z.object({
  id: z.string(),
  kind: z.literal("substructure"),
  query: z.string(),
  queryKind: z.enum(["smiles", "smarts"]),
  moleculeIds: z.array(z.string()).optional(),
  over: z.string().optional(),
});

export const filterSchema = z.discriminatedUnion("kind", [
  rangeFilter,
  categoryFilter,
  rowsFilter,
  substructureFilter,
]);
export const savedFilterSchema = z.discriminatedUnion("kind", [
  rangeFilter,
  categoryFilter,
  substructureFilter.omit({ moleculeIds: true, over: true }),
]);

/** One series: compounds under a scaffold-tree node, or matching an R-groups set's core
 * (exactly one of the two). */
const seriesMemberSchema = z.object({
  name: z.string(),
  scaffold: z.string().optional(),
  rgroupsId: z.string().optional(),
});

/** What a derived column set is computed from. R-groups sets are `rg1`, `rg2`, … ("Core A",
 * "Core B", …); there is at most one clusters set and one series set. */
export const derivedSpecSchema = z.discriminatedUnion("kind", [
  z.object({
    id: z.string(),
    kind: z.literal("rgroups"),
    coreSmiles: z.string(),
    name: z.string(),
  }),
  z.object({ id: z.literal("clusters"), kind: z.literal("clusters"), threshold: z.number() }),
  z.object({
    id: z.literal("series"),
    kind: z.literal("series"),
    members: z.array(seriesMemberSchema),
  }),
]);

/** How a saved view looks — never its data. ``labels`` names each referenced column key, so
 * what no longer resolves can be listed by name; ``derived`` says how to compute its
 * chemistry columns again. */
export const viewConfigSchema = z.object({
  config_version: z.number().int(),
  panels: z.array(panelSchema).max(MAX_PANELS),
  filters: z.array(savedFilterSchema).max(100),
  labels: z.record(z.string(), z.string()).default({}),
  derived: z.array(derivedSpecSchema).default([]),
});

export type ViewConfig = z.infer<typeof viewConfigSchema>;
