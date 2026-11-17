/** A field's label for display: the part after its group's prefix ("Counter · pIC50" in group
 * "Counter" → "pIC50" from "Counter"), else the whole label. */
export function fieldName(f: { label: string; group?: string }): { name: string; from?: string } {
  const prefix = f.group ? `${f.group} · ` : "";
  return prefix && f.label.startsWith(prefix) && f.label.length > prefix.length
    ? { name: f.label.slice(prefix.length), from: f.group }
    : { name: f.label };
}

const WORD_CHAR = /[\p{L}\p{N}]/u;

/** How well ``label`` matches lower-cased ``q``: 5 exactly, 4 at its start, 3 at a word's
 * start, 2 inside a word, 1 its letters in order, 0 not at all. */
function matchRank(label: string, q: string): number {
  const l = label.toLowerCase();
  if (l === q) return 5;
  if (l.startsWith(q)) return 4;
  let at = l.indexOf(q);
  if (at >= 0) {
    for (; at >= 0; at = l.indexOf(q, at + 1)) if (!WORD_CHAR.test(l[at - 1])) return 3;
    return 2;
  }
  const letters = q.replace(/\s+/g, "");
  let k = 0;
  for (const ch of l) if (ch === letters[k]) k++;
  return k === letters.length ? 1 : 0;
}

/** The fields whose label matches ``query``, best match first (then the shorter, then in order); all of
 * them for a blank query. */
export function rankFields<T extends { label: string }>(fields: T[], query: string): T[] {
  const q = query.trim().toLowerCase();
  if (!q) return fields;
  return fields
    .map((f, i) => ({ f, i, rank: matchRank(f.label, q) }))
    .filter((m) => m.rank > 0)
    .sort((a, b) => b.rank - a.rank || a.f.label.length - b.f.label.length || a.i - b.i)
    .map((m) => m.f);
}
