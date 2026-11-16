/** Mean and sample SD (n − 1) of ``values``: ``sd`` is null below two values, the whole
 * result null for none. */
export function meanSd(values: number[]): { mean: number; sd: number | null; n: number } | null {
  const n = values.length;
  if (n === 0) return null;
  const mean = values.reduce((s, v) => s + v, 0) / n;
  if (n < 2) return { mean, sd: null, n };
  const ss = values.reduce((s, v) => s + (v - mean) ** 2, 0);
  return { mean, sd: Math.sqrt(ss / (n - 1)), n };
}

/** Least-squares line through (``xs``, ``ys``); null below two distinct x values. */
export function linearFit(xs: number[], ys: number[]): { slope: number; intercept: number } | null {
  const n = xs.length;
  if (n < 2) return null;
  const mx = xs.reduce((s, v) => s + v, 0) / n;
  const my = ys.reduce((s, v) => s + v, 0) / n;
  let sxx = 0;
  let sxy = 0;
  for (let k = 0; k < n; k++) {
    sxx += (xs[k] - mx) ** 2;
    sxy += (xs[k] - mx) * (ys[k] - my);
  }
  if (sxx === 0) return null;
  const slope = sxy / sxx;
  return { slope, intercept: my - slope * mx };
}
