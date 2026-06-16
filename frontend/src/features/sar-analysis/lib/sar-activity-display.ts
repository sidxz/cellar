/**
 * SAR activity-display helpers — the potency ramp shared by the R-group table
 * and the heatmap. Pure; gated to `dr_curve` (lower-is-better) at the call site.
 * Both surfaces anchor on the server-supplied `activity_reference` (min over the
 * full scored set), so there is no client-side reference computation.
 */

/** Green→red potency ramp by fold-off from the most-potent reference (dr_curve only). */
export function potencyShade(scalar: number | null, reference: number | null): string {
  if (scalar == null || reference == null) return "";
  if (!Number.isFinite(scalar) || !Number.isFinite(reference) || reference <= 0) return "";
  const fold = scalar / reference;
  if (fold <= 1) return "bg-green-600/30 text-green-900 dark:text-green-100";
  if (fold <= 3) return "bg-green-500/20 text-green-900 dark:text-green-100";
  if (fold <= 10) return "bg-amber-500/20 text-amber-900 dark:text-amber-100";
  if (fold <= 100) return "bg-orange-500/25 text-orange-900 dark:text-orange-100";
  return "bg-red-600/30 text-red-900 dark:text-red-100";
}
