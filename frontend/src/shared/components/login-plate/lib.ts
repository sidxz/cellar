/** Geometry behind the login-page plate. Nothing here touches real data. */

/** Seeded random numbers, so every render draws the same plate. */
export function mulberry32(seed: number): () => number {
  let a = seed | 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** CSS custom properties for a style prop, which React's types do not know about. */
export function vars(values: Record<`--${string}`, string | number>): React.CSSProperties {
  return values as React.CSSProperties;
}

export interface TraceCurve {
  /** Horizontal shift of the midpoint, as a fraction of the curve's width. */
  dx: number;
  /** Steepness multiplier; 1 spans the width in about ten log units. */
  k: number;
}

/**
 * The wells that lie on a dose-response sigmoid drawn across the panel left
 * of the sign-in column: [row, col, order], with order counting up from the
 * curve's left end so a sweep can light them in turn. Where the curve is
 * steep every row it crosses is included, so the trace stays continuous,
 * and the band is `thickness` wells deep.
 */
export function tracePoints(
  rows: number,
  cols: number,
  pitch: number,
  panel: number,
  curve: TraceCurve,
  thickness = 3,
  /** With a source of randomness the trace is imperfect: some wells are
   *  skipped and some sit a row off, like a real read. */
  random?: () => number,
): Array<[row: number, col: number, order: number]> {
  const vw = Math.max(pitch, cols * pitch - panel);
  const vh = rows * pitch;
  const spanW = Math.min(vw * 0.72, 760);
  const spanH = Math.min(vh * 0.5, 400);
  const cx0 = vw / 2 + curve.dx * spanW;
  const cy0 = vh / 2;
  const yAt = (x: number) =>
    cy0 + spanH / 2 - spanH / (1 + Math.exp((-(x - cx0) / (spanW / 10)) * curve.k));

  const out: Array<[number, number, number]> = [];
  const seen = new Set<number>();
  const c0 = Math.floor((cx0 - spanW / 2) / pitch);
  const c1 = Math.ceil((cx0 + spanW / 2) / pitch);
  for (let c = c0; c <= c1; c++) {
    if (c < 0 || c >= cols) continue;
    const xc = c * pitch + pitch / 2;
    const ya = yAt(xc - pitch / 2);
    const yb = yAt(xc + pitch / 2);
    // the band is `thickness` wells deep, measured across the curve
    const half = ((thickness - 1) / 2) * pitch;
    const rA = Math.round((Math.min(ya, yb) - half - pitch / 2) / pitch);
    const rB = Math.round((Math.max(ya, yb) + half - pitch / 2) / pitch);
    for (let r = rA; r <= rB; r++) {
      if (random && random() < 0.12) continue;
      const rr = random && random() < 0.1 ? r + (random() < 0.5 ? -1 : 1) : r;
      if (rr < 0 || rr >= rows || seen.has(rr * cols + c)) continue;
      seen.add(rr * cols + c);
      out.push([rr, c, c - c0]);
    }
  }
  return out;
}

/** Random wells scattered over the panel left of the sign-in column: noise
 *  that glows on its own. [row, col, phase], phase in 0..1. */
export function noiseWells(
  rows: number,
  cols: number,
  pitch: number,
  panel: number,
  count: number,
  random: () => number,
): Array<[row: number, col: number, phase: number]> {
  const visibleCols = Math.max(1, Math.floor((cols * pitch - panel) / pitch));
  const out = new Map<number, [number, number, number]>();
  // a few extra draws cover collisions; a tiny plate may still yield fewer
  for (let i = 0; i < count * 3 && out.size < count; i++) {
    const r = Math.floor(random() * rows);
    const c = Math.floor(random() * visibleCols);
    if (!out.has(r * cols + c)) out.set(r * cols + c, [r, c, random()]);
  }
  return [...out.values()];
}
