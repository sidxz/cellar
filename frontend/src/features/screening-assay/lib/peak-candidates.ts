/** The peaks found in a position's traces (the peak-candidates read): which
 *  one a click on the plot means, and which other signal shows a step where
 *  the shown one has none. Pure. */

import type { PeakCandidateModel } from "@/shared/lib/api/model";

export type Candidate = PeakCandidateModel;

/** The candidate nearest to x, when it lies within reach; otherwise null. Of
 *  two equally near, the stronger. */
export function snapTarget(
  candidates: readonly Candidate[],
  x: number,
  reach: number,
): Candidate | null {
  let nearest: Candidate | null = null;
  let distance = reach;
  for (const c of candidates) {
    const d = Math.abs(c.value - x);
    if (d < distance || (d === distance && (!nearest || c.strength > nearest.strength))) {
      nearest = c;
      distance = d;
    }
  }
  return nearest;
}

/** Per signal, the candidate that stands alone inside the window: among those
 *  whose value lies in [low, high], the only one, or the strongest when it is
 *  at least twice as strong as the next; a signal without one is left out. */
export function hintsFor(
  window: { low: number; high: number },
  bySignal: ReadonlyMap<string, readonly Candidate[]>,
): { signal: string; value: number }[] {
  const hints: { signal: string; value: number }[] = [];
  for (const [signal, candidates] of bySignal) {
    const [first, second] = candidates
      .filter((c) => c.value >= window.low && c.value <= window.high)
      .sort((a, b) => b.strength - a.strength);
    if (first && (!second || first.strength >= 2 * second.strength)) {
      hints.push({ signal, value: first.value });
    }
  }
  return hints;
}
