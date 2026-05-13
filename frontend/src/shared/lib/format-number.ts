/**
 * Significant-figure aware number formatter for chemistry display.
 *
 * Default: 3 significant figures (industry standard for IC50/EC50/%inh).
 * - Values in [0.001, 1e6): formatted as a fixed-decimal string with trailing
 *   zeros stripped. e.g. 53.399 → "53.4", 2.236 → "2.24", 1245.7 → "1250".
 * - Values outside that range: scientific notation. e.g. 1.23e-5, 1.23e+6.
 * - null/undefined/NaN/Infinity → "—".
 *
 * Why not just `.toPrecision(3)`? Because `toPrecision` flips to scientific
 * notation for integers with more digits than the requested precision (e.g.
 * `(1245).toPrecision(3) === "1.25e+3"`), which is the wrong default for a
 * chemist scanning a column of µM values.
 */
export function formatMeasurementValue(value: number | null | undefined, sigFigs = 3): string {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value === 0) return "0";

  const abs = Math.abs(value);
  // Scientific notation outside the human-readable band.
  if (abs < 1e-3 || abs >= 1e6) {
    return value.toExponential(sigFigs - 1);
  }

  const magnitude = Math.floor(Math.log10(abs));

  // Large integers — round to sig figs but keep fixed-form output.
  if (magnitude >= sigFigs) {
    const rounded = Number(value.toPrecision(sigFigs));
    return rounded.toString();
  }

  // Sub-1 and small-positive values — fixed decimals with trailing-zero strip.
  const decimals = sigFigs - 1 - magnitude;
  let s = value.toFixed(decimals);
  if (s.includes(".")) {
    s = s.replace(/0+$/, "").replace(/\.$/, "");
  }
  return s;
}

export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}
