import Papa from "papaparse";

/** Matches the backend's per-term cap (`MAX_KEYWORD_VALUES` in `_field_clauses.py`). */
export const MAX_KEYWORD_VALUES = 1000;

// A comma between locants belongs to the chemical name, not the list: "2,4-dinitrophenol",
// "N,N-dimethylformamide", "1,1'-biphenyl", "(2S,3R)-threonine". It sits in a run of locants
// that begins the word and ends at a hyphen or bracket.
// ponytail: a locant-shaped ID list ("S-1,S-2") stays one value; quotes or new lines split it.
const LOCANT = String.raw`(?:\d+[A-Za-z]?|[NOSP])['′″]*`;
const LOCANT_COMMA = new RegExp(
  String.raw`(?<=(?:^|[^\w'′″])(?:${LOCANT},)*${LOCANT}),(?=(?:${LOCANT},)*${LOCANT}[-()[\]])`,
  "g",
);
const KEPT_COMMA = "";

/** Accept CSV and pasted spreadsheet cells while keeping quoted commas and locants in names. */
export function parseKeywordValues(text: string): string[] {
  const normalized = text
    .replace(LOCANT_COMMA, KEPT_COMMA)
    .replace(/"(?:[^"]|"")*"|[;\t]/g, (part) => (part.startsWith('"') ? part : ","));
  const { data } = Papa.parse<string[]>(normalized, {
    delimiter: ",",
    skipEmptyLines: "greedy",
  });
  return [
    ...new Set(
      data
        .flat()
        .map((value) => value.replaceAll(KEPT_COMMA, ",").trim())
        .filter(Boolean),
    ),
  ];
}

/** One value per line, quoted only where parsing it bare would change it. */
export function formatKeywordValues(values: string[]): string {
  return values
    .map((value) => {
      const [parsed, ...rest] = parseKeywordValues(value);
      return parsed === value && rest.length === 0 ? value : `"${value.replaceAll('"', '""')}"`;
    })
    .join("\n");
}
