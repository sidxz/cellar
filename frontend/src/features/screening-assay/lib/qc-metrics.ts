/** Helpers for reading run.qc_metrics.
 *
 * The calc engine emits a per-plate dict:
 *   { z_prime: { plate_id: { z_prime, classification, pos_mean, ... } } }
 * Display sites need either the per-plate breakdown or a single summary
 * scalar. Both are implemented here so call sites cannot accidentally
 * call .toFixed() on a dict.
 */

/** Z' factor quality classification.
 *
 * Industry convention (Zhang et al., 1999):
 *   Z' >= 0.5  → Excellent (large dynamic range, low noise)
 *   0 <= Z' < 0.5 → Marginal (assay is usable but signal/noise is tight)
 *   Z' < 0     → Poor (controls overlap; assay does not separate hits)
 */
export type ZPrimeQuality = "excellent" | "marginal" | "poor";

export const Z_PRIME_EXCELLENT_THRESHOLD = 0.5;
export const Z_PRIME_MARGINAL_THRESHOLD = 0;

export function classifyZPrime(value: number): ZPrimeQuality {
  if (value >= Z_PRIME_EXCELLENT_THRESHOLD) return "excellent";
  if (value >= Z_PRIME_MARGINAL_THRESHOLD) return "marginal";
  return "poor";
}

export interface PlateQcEntry {
  z_prime?: number;
  classification?: string;
  pos_mean?: number;
  pos_sd?: number;
  neg_mean?: number;
  neg_sd?: number;
  s2b?: number;
}

/** Per-plate Z' map. Returns {} if absent or in legacy/unknown shape. */
export function readPerPlateQc(
  qcMetrics: Record<string, unknown> | null | undefined,
): Record<string, PlateQcEntry> {
  if (!qcMetrics) return {};
  const raw = qcMetrics.z_prime;
  if (!raw || typeof raw !== "object") return {};
  return raw as Record<string, PlateQcEntry>;
}

/** Worst (minimum) Z' across plates. Used for run-level summary badges.
 *
 * Falls back to a scalar `z_prime` if `qc_metrics.z_prime` is a number
 * (defensive — older runs might still carry that shape).
 */
export function worstZPrime(qcMetrics: Record<string, unknown> | null | undefined): number | null {
  if (!qcMetrics) return null;
  const raw = qcMetrics.z_prime;
  if (typeof raw === "number") return raw;
  const perPlate = readPerPlateQc(qcMetrics);
  const values: number[] = [];
  for (const v of Object.values(perPlate)) {
    if (typeof v?.z_prime === "number") values.push(v.z_prime);
  }
  return values.length > 0 ? Math.min(...values) : null;
}
