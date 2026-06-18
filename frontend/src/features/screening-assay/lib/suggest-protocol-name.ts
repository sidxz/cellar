/** Provenance-aware default protocol name derived from the structured facets
 *  the chemist already supplied. One-click, fully editable, never enforced. */
export function suggestProtocolName(input: {
  targetNames: string[];
  readoutNames: string[];
  protocolType: string;
}): string {
  const words = input.protocolType.split("_");
  const typeLabel = input.protocolType
    ? [words[0].charAt(0).toUpperCase() + words[0].slice(1), ...words.slice(1)].join(" ")
    : "";
  const segments = [
    input.targetNames.filter(Boolean).join(" / "),
    input.readoutNames.filter(Boolean)[0] ?? "",
    typeLabel,
  ].filter(Boolean);
  return segments.join(" · ");
}
