/**
 * Activity rollup for scaffold-tree node coloring.
 *
 * Reads each molecule's ActivityValue payload (the wire shape returned by
 * useCollectionSearch — protocol_id -> {intercept_values: [...]}), takes
 * the first EC/IC intercept value per molecule, computes pIC50 (= -log10
 * value), and computes the median across the subtree mols. ND ("nd"
 * qualifier) and non-positive values are excluded — they are not zero, they
 * are "no info".
 *
 * The loose input types allow callers to pass either the orval-generated
 * ActivityValue dicts or hand-rolled equivalents; only the fields read here
 * are required.
 */

export type ActivityRollupBin = "active_high" | "active_mid" | "weak" | "inactive";

// Loose shape — consumers can pass either orval-generated ActivityValue dicts
// or hand-rolled equivalents. The fields we read are documented inline.
type InterceptValueLike = {
  kind?: string;
  level?: number;
  /** Raw concentration value in molar units (e.g. 1e-6 for 1 µM).
   *  null / undefined → treated as ND. Non-positive → excluded (log undefined). */
  value?: number | null;
  /** "=" | "<" | ">" | "nd" — same wire semantics as ActivityValue.qualifier. */
  qualifier?: string;
};

type ActivityValueLike = {
  intercept_values?: InterceptValueLike[] | null;
};

type ActivityDataLike = Record<string, Record<string, ActivityValueLike>>;

/** Thresholds in descending order — first match wins. */
const PIC50_BINS: ReadonlyArray<{ threshold: number; bin: ActivityRollupBin }> = [
  { threshold: 8.0, bin: "active_high" },
  { threshold: 6.0, bin: "active_mid" },
  { threshold: 5.0, bin: "weak" },
];

/**
 * Maps a median pIC50 to one of four activity bins:
 *   active_high  pIC50 >= 8   (EC50 <= 10 nM)
 *   active_mid   pIC50 >= 6   (EC50 <= 1 µM)
 *   weak         pIC50 >= 5   (EC50 <= 10 µM)
 *   inactive     pIC50 <  5
 *
 * Returns null when input is null or NaN.
 */
export function classifyActivity(pic50: number | null): ActivityRollupBin | null {
  if (pic50 === null || pic50 === undefined || Number.isNaN(pic50)) return null;
  for (const { threshold, bin } of PIC50_BINS) {
    if (pic50 >= threshold) return bin;
  }
  return "inactive";
}

/**
 * Computes the median pIC50 for a set of molecules against a single protocol.
 *
 * For each molecule the first intercept value in `activity[molId][protocolId]
 * .intercept_values` that has a valid, positive value and a non-ND qualifier
 * is converted to pIC50 = -log10(value). ND entries (qualifier === "nd",
 * null value, or non-positive value) are silently excluded — they carry no
 * quantitative information.
 *
 * Returns null when no valid values exist (all ND, no protocol entry, empty
 * mol list).
 */
export function medianPic50ForMols(
  molIds: string[],
  activity: ActivityDataLike | undefined | null,
  protocolId: string,
): number | null {
  if (!activity) return null;

  const pic50s: number[] = [];

  for (const mid of molIds) {
    const proto = activity[mid]?.[protocolId];
    if (!proto?.intercept_values) continue;

    for (const iv of proto.intercept_values) {
      // ND qualifier → no information; skip.
      if (iv.qualifier === "nd") continue;
      // Null / undefined value → no information; skip.
      if (iv.value == null) continue;
      // Non-positive value → log10 is undefined; skip.
      if (iv.value <= 0) continue;

      pic50s.push(-Math.log10(iv.value));
      // One value per molecule — take the first valid intercept and move on.
      break;
    }
  }

  if (pic50s.length === 0) return null;

  pic50s.sort((a, b) => a - b);
  const mid = Math.floor(pic50s.length / 2);
  return pic50s.length % 2 === 0
    ? (pic50s[mid - 1] + pic50s[mid]) / 2
    : pic50s[mid];
}
