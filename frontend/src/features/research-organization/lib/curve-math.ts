/**
 * Generate fitted 4PL (four-parameter logistic) sigmoid curve points on a
 * logarithmic x-scale. Used for rendering dose-response curves in both
 * inline grid cells and the compound detail panel.
 *
 * Returns empty arrays when the inputs would produce non-finite results
 * (e.g. ic50 === 0 or fewer than 2 positive x-values in rawData).
 */
export function generate4PLPoints(
  rawData: Array<{ x: number; y: number }>,
  ic50: number,
  hillSlope: number,
  top: number,
  bottom: number,
  options?: { numPoints?: number; rangeExtension?: number },
): { x: number[]; y: number[] } {
  if (ic50 === 0 || !isFinite(ic50)) return { x: [], y: [] };

  const xValues = rawData.map((p) => p.x).filter((v) => v > 0);
  if (xValues.length < 2) return { x: [], y: [] };

  const xMin = Math.min(...xValues);
  const xMax = Math.max(...xValues);
  const ext = options?.rangeExtension ?? 0.5;
  const numPoints = options?.numPoints ?? 80;

  const logMin = Math.log10(xMin) - ext;
  const logMax = Math.log10(xMax) + ext;
  const x: number[] = [];
  const y: number[] = [];

  for (let i = 0; i <= numPoints; i++) {
    const logX = logMin + (i / numPoints) * (logMax - logMin);
    const xVal = Math.pow(10, logX);
    const yVal = bottom + (top - bottom) / (1 + Math.pow(xVal / ic50, hillSlope));
    if (isFinite(yVal)) {
      x.push(xVal);
      y.push(yVal);
    }
  }

  return { x, y };
}
