/** Temperature windows proposed around a reference's peaks, and a window's
 *  label. Pure. */

export interface ProposedWindow {
  peak: number;
  low: number;
  high: number;
}

const round1 = (v: number) => Math.round(v * 10) / 10;

/** One range per peak that lies in no existing window. Boundaries are the
 *  midpoints between neighboring peaks (all of them, also those an existing
 *  window already holds) and the outer edges are the trace's ends, rounded to
 *  0.1. A range is cut back to an existing window's limit where the two would
 *  overlap. */
export function proposeWindows(
  peaks: readonly number[],
  traceRange: readonly [number, number],
  existing: readonly { low: number; high: number }[],
): ProposedWindow[] {
  const sorted = [...peaks].sort((a, b) => a - b);
  return sorted.flatMap((peak, i) => {
    if (existing.some((e) => peak >= e.low && peak <= e.high)) return [];
    const low = i === 0 ? traceRange[0] : (sorted[i - 1] + peak) / 2;
    const high = i === sorted.length - 1 ? traceRange[1] : (peak + sorted[i + 1]) / 2;
    // The peak is in no existing window, so each one lies wholly below or above it.
    const below = existing.filter((e) => e.high < peak).map((e) => e.high);
    const above = existing.filter((e) => e.low > peak).map((e) => e.low);
    return [{ peak, low: Math.max(round1(low), ...below), high: Math.min(round1(high), ...above) }];
  });
}

/** `Main 50–85 °C`. */
export function windowLabel(w: { window: string; low: number; high: number }): string {
  return `${w.window} ${w.low}–${w.high} °C`;
}
