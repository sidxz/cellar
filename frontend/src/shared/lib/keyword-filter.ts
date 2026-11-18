/**
 * A `filter` for `<Command>`: an item matches when every word typed appears, contiguously and in
 * any case, in its `keywords`. Items whose first keyword — the label — starts with the first word
 * rank above the rest.
 *
 * Use it where the fuzzy default is too loose, such as a catalog of short names: the default
 * accepts letters scattered across every field, so "pptt" matched hundreds of targets. The item's
 * `value` is never searched, so it can be an opaque id.
 */
export function keywordFilter(_value: string, search: string, keywords: string[] = []): number {
  const terms = search.toLowerCase().split(/\s+/).filter(Boolean);
  const text = keywords.join(" ").toLowerCase();
  if (!text || !terms.every((term) => text.includes(term))) return 0;
  return terms[0] && text.startsWith(terms[0]) ? 1 : 0.5;
}
