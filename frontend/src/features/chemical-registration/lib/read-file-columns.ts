import { parseCollectionImportFile } from "@/features/research-organization/lib/parse-collection-import-csv";

/** Must match SDF_TITLE_HEADER in backend bulk_column_mapping.py. */
export const SDF_TITLE_HEADER = "Title line";

const SAMPLE_COUNT = 3;
const SDF_RECORDS_SCANNED = 50;

export interface FileColumns {
  headers: string[];
  /** First few distinct non-empty values per header, for the mapping screen. */
  samples: Record<string, string[]>;
}

function samplesFrom(headers: string[], rows: Record<string, string>[]): FileColumns["samples"] {
  const samples: Record<string, string[]> = {};
  for (const h of headers) {
    const seen: string[] = [];
    for (const row of rows) {
      const v = (row[h] ?? "").trim();
      if (v && !seen.includes(v)) seen.push(v);
      if (seen.length >= SAMPLE_COUNT) break;
    }
    samples[h] = seen;
  }
  return samples;
}

/** The title line and `> <Name>` data items of the first records of an SDF file. */
export function readSdfColumns(text: string): FileColumns {
  const records = text.split(/^\$\$\$\$\s*$/m).slice(0, SDF_RECORDS_SCANNED);
  const headers = [SDF_TITLE_HEADER];
  const rows: Record<string, string>[] = [];
  for (const rec of records) {
    const lines = rec.replace(/^\r?\n/, "").split(/\r?\n/);
    if (lines.every((l) => !l.trim())) continue;
    const row: Record<string, string> = { [SDF_TITLE_HEADER]: (lines[0] ?? "").trim() };
    for (let i = 0; i < lines.length; i++) {
      const m = /^>.*<([^>]+)>/.exec(lines[i]);
      if (!m) continue;
      const name = m[1];
      const values: string[] = [];
      for (let j = i + 1; j < lines.length && lines[j].trim() !== ""; j++) values.push(lines[j]);
      row[name] = values.join("\n").trim();
      if (!headers.includes(name)) headers.push(name);
    }
    rows.push(row);
  }
  return { headers, samples: samplesFrom(headers, rows) };
}

/**
 * Headers and sample values of a bulk-registration file, for the mapping step.
 * The server parses the file for real; this only draws the screen.
 */
export async function readFileColumns(
  file: File,
  format: "csv" | "xlsx" | "sdf",
): Promise<FileColumns> {
  if (format === "sdf") {
    // ponytail: reads the whole SDF as text to scan 50 records; slice the File if huge files are slow.
    const text =
      typeof file.text === "function" ? await file.text() : await new Response(file).text();
    return readSdfColumns(text);
  }
  // ponytail: parses every row of a CSV/XLSX in the browser just for headers and samples; stream if 50 MB files are slow.
  const parsed = await parseCollectionImportFile(file);
  if (parsed.kind === "error") throw new Error(parsed.message);
  return { headers: parsed.headers, samples: samplesFrom(parsed.headers, parsed.rows) };
}
