/** A header as the import wizards compare it: lower case, letters and digits only. */
export const normHeader = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "");

/** Share of a saved mapping's headers (`refs`) the file has, compared by `normHeader`; 0 when none are saved. */
export function headerMatchScore(refs: string[], headers: string[]): number {
  if (refs.length === 0) return 0;
  const file = new Set(headers.map(normHeader));
  return refs.filter((r) => file.has(normHeader(r))).length / refs.length;
}
