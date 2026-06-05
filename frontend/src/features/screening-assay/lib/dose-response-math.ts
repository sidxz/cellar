/**
 * Pure math helpers for dose-response chart rendering.
 *
 * All functions here are side-effect-free, have no DOM or React dependencies,
 * and can be unit-tested in Node/vitest without a browser context.
 */

import type { DoseResponseCurve } from "../types";
import { CURVE_FIT_POINTS, generate4PLPoints } from "./dose-response-display";

// ─── Degenerate-fit guard ─────────────────────────────────────────────────────

/**
 * A curve has no meaningful sigmoid to draw when classified Inactive or
 * the fit produced degenerate parameters. ``ec50_at_bound`` curves are
 * still rendered (with an amber warning badge) so the user can see the
 * data and the extrapolated fit; only truly inactive / zero curves are
 * suppressed here.
 */
export function isDegenerateFit(curve: DoseResponseCurve): boolean {
  return (
    curve.curve_class === "inactive" ||
    !Number.isFinite(curve.fitted_value) ||
    curve.fitted_value <= 0 ||
    curve.hill_slope === 0
  );
}

// ─── Curve generation ─────────────────────────────────────────────────────────

/** Plotly-friendly wrapper around the shared 4PL evaluator. Kept as a
 *  thin function so existing callers don't need to thread the curve
 *  destructure through ``generate4PLPoints``. */
export function generate4PLCurve(
  curve: DoseResponseCurve,
  xMin: number,
  xMax: number,
): { x: number[]; y: number[] } {
  const { x, y } = generate4PLPoints(curve, xMin, xMax, CURVE_FIT_POINTS + 1);
  return { x, y };
}

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

// ─── Replicate statistics ─────────────────────────────────────────────────────

/** Group points by concentration, return mean ± SD arrays for error bars */
export function computeReplicateStats(
  x: number[],
  y: number[],
): {
  meanX: number[];
  meanY: number[];
  sdY: number[];
  replicateX: number[];
  replicateY: number[];
} {
  if (x.length === 0) {
    return { meanX: [], meanY: [], sdY: [], replicateX: [], replicateY: [] };
  }

  // Group by concentration (use string key to avoid float equality issues)
  const groups = new Map<string, { conc: number; responses: number[] }>();
  for (let i = 0; i < x.length; i++) {
    const key = x[i].toPrecision(10);
    if (!groups.has(key)) groups.set(key, { conc: x[i], responses: [] });
    groups.get(key)?.responses.push(y[i]);
  }

  const meanX: number[] = [];
  const meanY: number[] = [];
  const sdY: number[] = [];
  const replicateX: number[] = [];
  const replicateY: number[] = [];

  for (const { conc, responses } of groups.values()) {
    const mean = responses.reduce((a, b) => a + b, 0) / responses.length;
    meanX.push(conc);
    meanY.push(mean);

    if (responses.length > 1) {
      const variance =
        responses.reduce((sum, v) => sum + (v - mean) ** 2, 0) / (responses.length - 1);
      sdY.push(Math.sqrt(variance));
    } else {
      sdY.push(0);
    }

    // Individual replicates for scatter layer
    if (responses.length > 1) {
      for (const resp of responses) {
        replicateX.push(conc);
        replicateY.push(resp);
      }
    }
  }

  return { meanX, meanY, sdY, replicateX, replicateY };
}

// ─── Display helpers ──────────────────────────────────────────────────────────

/** R² color class */
export function rSquaredColor(r2: number): string {
  if (r2 >= 0.9) return "text-green-400";
  if (r2 >= 0.8) return "text-yellow-400";
  return "text-destructive";
}

/** Whether a Y-axis normalization belongs to the percent-scale family that
 *  the [85,110]/[-10,10]/[0.9,1.1] constraint defaults are calibrated for. */
export function isPercentNormalization(norm: string | null | undefined): boolean {
  return (
    norm === "percent_inhibition" || norm === "percent_activation" || norm === "percent_control"
  );
}
