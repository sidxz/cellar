// Ray-casting point-in-polygon.

export interface Point {
  x: number;
  y: number;
}

export interface IdPoint {
  moleculeId: string;
  x: number;
  y: number;
}

export function pointInPolygon(p: Point, poly: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i].x, yi = poly[i].y;
    const xj = poly[j].x, yj = poly[j].y;
    const intersect =
      ((yi > p.y) !== (yj > p.y)) &&
      p.x < ((xj - xi) * (p.y - yi)) / (yj - yi || Number.EPSILON) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

export function idsInsidePolygon(points: IdPoint[], poly: Point[]): string[] {
  if (poly.length < 3) return [];
  return points.filter((pt) => pointInPolygon(pt, poly)).map((pt) => pt.moleculeId);
}

export interface PlotlySelectionEvent {
  /** Lasso drag: polygon vertices in DATA coordinates. */
  lassoPoints?: { x: number[]; y: number[] };
  /** Box select: [x0, x1] / [y0, y1] in DATA coordinates. */
  range?: { x: number[]; y: number[] };
  /** Per-point selection payload (fragile on scattergl — fallback only). */
  points?: { curveNumber?: number; pointNumber?: number; pointIndex?: number }[];
}

/**
 * Resolve the molecule ids a Plotly lasso/box selection covers.
 *
 * Prefers the data-space geometry (`lassoPoints` / `range`) and tests membership
 * against our own `points` via ray-casting — this is robust on BOTH `scatter`
 * and `scattergl`, where Plotly's per-point `pointNumber` / `customdata` plumbing
 * is historically unreliable. Falls back to `pointNumber` indexing only when no
 * geometry is present.
 */
export function selectedIdsFromPlotlyEvent(
  ev: PlotlySelectionEvent | null | undefined,
  points: IdPoint[],
): string[] {
  if (!ev) return [];

  if (ev.lassoPoints?.x && ev.lassoPoints.x.length >= 3) {
    const lx = ev.lassoPoints.x;
    const ly = ev.lassoPoints.y;
    const poly = lx.map((x, i) => ({ x, y: ly[i] }));
    return idsInsidePolygon(points, poly);
  }

  if (ev.range?.x && ev.range?.y) {
    const [x0, x1] = ev.range.x;
    const [y0, y1] = ev.range.y;
    const poly = [
      { x: x0, y: y0 },
      { x: x1, y: y0 },
      { x: x1, y: y1 },
      { x: x0, y: y1 },
    ];
    return idsInsidePolygon(points, poly);
  }

  if (Array.isArray(ev.points) && ev.points.length > 0) {
    return ev.points
      .filter((p) => (p.curveNumber ?? 0) === 0)
      .map((p) => {
        const idx = p.pointNumber ?? p.pointIndex;
        return typeof idx === "number" ? points[idx]?.moleculeId : undefined;
      })
      .filter((id): id is string => Boolean(id));
  }

  return [];
}
