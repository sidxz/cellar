interface OverlayPoint {
  moleculeId: string;
  x: number;
  y: number;
}

/**
 * Build the overlay traces drawn ON TOP of the base + star traces:
 *   - in-basket members → emerald open ring ("in your cart")
 *   - region-pick candidates → violet open star ("picked from this region, not yet added")
 *
 * Returns 0–2 traces (basket first so candidates render above it). Pure — unit
 * tested without Plotly.
 */
export function buildOverlayTraces(
  points: OverlayPoint[],
  basketIds: Set<string> | undefined,
  regionPickIds: Set<string> | undefined,
  traceType: string,
): Record<string, unknown>[] {
  const traces: Record<string, unknown>[] = [];

  if (basketIds && basketIds.size > 0) {
    const members = points.filter((p) => basketIds.has(p.moleculeId));
    if (members.length > 0) {
      traces.push({
        type: traceType,
        mode: "markers",
        x: members.map((p) => p.x),
        y: members.map((p) => p.y),
        marker: {
          symbol: "circle-open",
          size: 14,
          line: { width: 2, color: "#059669" },
        },
        hoverinfo: "skip",
      });
    }
  }

  if (regionPickIds && regionPickIds.size > 0) {
    const members = points.filter((p) => regionPickIds.has(p.moleculeId));
    if (members.length > 0) {
      traces.push({
        type: traceType,
        mode: "markers",
        x: members.map((p) => p.x),
        y: members.map((p) => p.y),
        marker: {
          symbol: "star-open",
          size: 16,
          line: { width: 1.5, color: "#7c3aed" },
        },
        hoverinfo: "skip",
      });
    }
  }

  return traces;
}
