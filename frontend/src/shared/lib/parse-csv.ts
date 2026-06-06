import Papa from "papaparse";

/**
 * Result of parsing a CSV source into headers + row objects.
 *
 * On success, `headers` is the trimmed header row (in file order) and `rows`
 * is one object per data row, keyed by header with whitespace-trimmed string
 * values. On failure, `message` describes the parse error.
 */
export type ParsedCsv =
  | { kind: "ok"; headers: string[]; rows: Record<string, string>[] }
  | { kind: "error"; message: string };

/**
 * Parse CSV/TSV text into raw rows (arrays of trimmed string cells) using
 * PapaParse, with delimiter auto-detection (comma or tab).
 *
 * Use this for *headerless / positional* formats where columns are read by
 * index, not by name (e.g. a pasted well-map). Like {@link parseCsv}, it
 * correctly handles quoted fields and embedded commas — unlike a naive
 * `line.split(/[,\t]/)`. Empty lines are skipped; every cell is a trimmed
 * string. The caller is responsible for header detection and validation.
 */
export function parseCsvRows(text: string): string[][] {
  const result = Papa.parse<string[]>(text, {
    header: false,
    skipEmptyLines: true,
  });
  return (result.data ?? []).map((row) => row.map((cell) => (cell ?? "").trim()));
}

/**
 * Parse CSV text or a CSV `File` into headers + row objects using PapaParse.
 *
 * This is the single shared CSV parser for the app. Unlike naive
 * `split("\n")`/`split(",")` parsers it correctly handles quoted fields,
 * embedded commas, and CRLF line endings, so a compound name containing a
 * comma round-trips intact.
 *
 * - The first row is treated as the header (header names are used verbatim, as
 *   PapaParse emits them, so row objects key off the exact header text).
 * - Empty lines are skipped.
 * - Every cell value is coerced to a trimmed string (missing cells become "").
 * - A source with no detectable headers, or any PapaParse error, resolves to
 *   `{ kind: "error" }`.
 */
export async function parseCsv(input: string | File): Promise<ParsedCsv> {
  return new Promise((resolve) => {
    const config = {
      header: true,
      skipEmptyLines: true as const,
      complete: (results: Papa.ParseResult<Record<string, string>>) => {
        if (results.errors.length > 0) {
          resolve({ kind: "error", message: results.errors[0].message });
          return;
        }
        const headers = results.meta.fields ?? [];
        if (headers.length === 0) {
          resolve({ kind: "error", message: "no headers detected" });
          return;
        }
        const rows = results.data.map((r) => {
          const norm: Record<string, string> = {};
          for (const h of headers) norm[h] = (r[h] ?? "").trim();
          return norm;
        });
        resolve({ kind: "ok", headers, rows });
      },
    };
    // Papa.parse's string and File overloads take structurally identical
    // configs; branch on the input type instead of casting the union.
    if (typeof input === "string") {
      Papa.parse<Record<string, string>>(input, config);
    } else {
      Papa.parse<Record<string, string>>(input, config);
    }
  });
}
