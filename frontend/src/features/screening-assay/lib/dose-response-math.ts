/**
 * Cellar-only dose-response helpers.
 *
 * The curve math the chart draws with — `isDegenerateFit`, `generate4PLCurve`,
 * `computeReplicateStats`, `rSquaredColor` — now lives in
 * `@structflo/components/dose-response` beside the renderer that uses it.
 * What stays here is cellar's own: point extraction for tables and the
 * percent-scale test the constraint defaults branch on.
 */

// ─── Data extraction ──────────────────────────────────────────────────────────

/** Extract (concentration, response) pairs from raw_data / excluded_points */
export function extractPoints(points: Array<Record<string, unknown>> | null): {
  x: number[];
  y: number[];
  reasons: (string | null)[];
} {
  if (!points || points.length === 0) return { x: [], y: [], reasons: [] };
  const xs: number[] = [];
  const ys: number[] = [];
  const reasons: (string | null)[] = [];
  for (const pt of points) {
    const conc = pt.concentration ?? pt.x;
    const resp = pt.response ?? pt.y;
    if (typeof conc === "number" && typeof resp === "number") {
      xs.push(conc);
      ys.push(resp);
      reasons.push(typeof pt.reason === "string" ? pt.reason : null);
    }
  }
  return { x: xs, y: ys, reasons };
}

// ─── Display helpers ──────────────────────────────────────────────────────────

/** Whether a Y-axis normalization belongs to the percent-scale family that
 *  the [85,110]/[-10,10]/[0.9,1.1] constraint defaults are calibrated for. */
export function isPercentNormalization(norm: string | null | undefined): boolean {
  return (
    norm === "percent_inhibition" || norm === "percent_activation" || norm === "percent_control"
  );
}
