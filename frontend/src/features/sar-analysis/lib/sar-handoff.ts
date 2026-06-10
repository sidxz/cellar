const KEY = "cellar:sar-handoff";

export interface SarHandoff {
  coreSmiles: string;
  moleculeIds: string[];
}

export function stashSarHandoff(payload: SarHandoff): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(payload));
  } catch {
    /* sessionStorage unavailable — ignore */
  }
}

/** Reads and clears the stash (one-shot). Returns null if absent/invalid. */
export function readSarHandoff(): SarHandoff | null {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    if (!raw) return null;
    window.sessionStorage.removeItem(KEY);
    const parsed = JSON.parse(raw) as SarHandoff;
    if (typeof parsed?.coreSmiles !== "string" || !Array.isArray(parsed?.moleculeIds)) return null;
    return parsed;
  } catch {
    return null;
  }
}
