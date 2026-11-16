import type { OverlayConfig, PanelConfig } from "../../store/workbench-store";
import type { Dataset } from "../../types";
import type { Facet, Figure } from "../traces/common";
import { type OverlayKind, overlayOptions } from "./options";
import { drawBands, drawDriftBands, drawTrends, drawZPrime } from "./qc";

/** What overlays add to a figure. Overlay traces carry no ``customdata``, so they are never
 * selectable; ``notes`` join the panel's footer note. */
export interface OverlayParts {
  traces: Record<string, unknown>[];
  shapes: Record<string, unknown>[];
  annotations: Record<string, unknown>[];
  notes: string[];
}

export const EMPTY_PARTS: OverlayParts = { traces: [], shapes: [], annotations: [], notes: [] };

type Draw = (ds: Dataset, panel: PanelConfig, mask: Uint8Array, facets: Facet[]) => OverlayParts;

/** The drawer of each overlay kind. */
const DRAW: Partial<Record<OverlayKind, Draw>> = {
  bands: drawBands,
  driftBand: drawDriftBands,
  trend: drawTrends,
  zPrime: drawZPrime,
};

/** The kinds ``o`` switches on (empty lists and unset values are off). */
function switchedOn(o: OverlayConfig): OverlayKind[] {
  const on: (OverlayKind | false | undefined)[] = [
    o.bands && "bands",
    o.drift === "band" && "driftBand",
    o.drift === "trend" && "trend",
    o.zPrime && "zPrime",
    o.refLine !== undefined && "refLine",
    o.limits && "limits",
    Boolean(o.lipe?.length) && "lipe",
    Boolean(o.selectivity?.length) && "selectivity",
  ];
  return on.filter((k): k is OverlayKind => Boolean(k));
}

/** The overlays ``panel`` has switched on that it can draw here, laid into ``facets``. */
export function buildOverlays(
  ds: Dataset,
  panel: PanelConfig,
  mask: Uint8Array,
  facets: Facet[],
): OverlayParts {
  if (!panel.overlays) return EMPTY_PARTS;
  const options = overlayOptions(ds, panel);
  const kinds = switchedOn(panel.overlays).filter((k) => options[k] === true);
  const parts = kinds
    // Drift bands replace the flat control bands.
    .filter((k) => k !== "bands" || !kinds.includes("driftBand"))
    .flatMap((k) => DRAW[k]?.(ds, panel, mask, facets) ?? []);
  if (parts.length === 0) return EMPTY_PARTS;
  return {
    traces: parts.flatMap((p) => p.traces),
    shapes: parts.flatMap((p) => p.shapes),
    annotations: parts.flatMap((p) => p.annotations),
    // Bands and trends both say when a facet has no control wells: once is enough.
    notes: [...new Set(parts.flatMap((p) => p.notes))],
  };
}

const inLegend = (mark: Record<string, unknown>) => mark.showlegend === true;

/** ``fig`` with ``parts`` drawn after its own traces, shapes and annotations, the legend on
 * when a part has an entry, and the notes after the figure's own. */
export function mergeOverlays(fig: Figure, parts: OverlayParts): Figure {
  const { traces, shapes, annotations, notes } = parts;
  if (!traces.length && !shapes.length && !annotations.length && !notes.length) return fig;
  const layout = fig.layout;
  const own = (key: string) => (layout[key] as Record<string, unknown>[] | undefined) ?? [];
  return {
    ...fig,
    data: [...fig.data, ...traces],
    layout: {
      ...layout,
      shapes: [...own("shapes"), ...shapes],
      annotations: [...own("annotations"), ...annotations],
      ...(traces.some(inLegend) || shapes.some(inLegend) ? { showlegend: true } : {}),
    },
    note: [fig.note, ...notes].filter(Boolean).join(" · ") || null,
  };
}
