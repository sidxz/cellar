/** Provenance-aware default protocol name derived from the structured facets
 *  the chemist already supplied. One-click, fully editable, never enforced. */
export function suggestProtocolName(input: {
  targetNames: string[];
  readoutNames: string[];
  typeLabel: string;
}): string {
  const segments = [
    input.targetNames.filter(Boolean).join(" / "),
    input.readoutNames.filter(Boolean)[0] ?? "",
    input.typeLabel,
  ].filter(Boolean);
  return segments.join(" · ");
}
