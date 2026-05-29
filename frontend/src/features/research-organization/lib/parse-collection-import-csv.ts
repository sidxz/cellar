import Papa from "papaparse";

export type ParsedCsv =
  | { kind: "ok"; headers: string[]; rows: Record<string, string>[] }
  | { kind: "error"; message: string };

export async function parseCollectionImportCsv(
  input: string | File,
): Promise<ParsedCsv> {
  return new Promise((resolve) => {
    Papa.parse(input as unknown as File, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        if (results.errors.length > 0) {
          resolve({ kind: "error", message: results.errors[0].message });
          return;
        }
        const headers = results.meta.fields ?? [];
        if (headers.length === 0) {
          resolve({ kind: "error", message: "no headers detected" });
          return;
        }
        const rows = (results.data as Record<string, string>[]).map((r) => {
          const norm: Record<string, string> = {};
          for (const h of headers) norm[h] = (r[h] ?? "").trim();
          return norm;
        });
        resolve({ kind: "ok", headers, rows });
      },
    });
  });
}

export function buildCollectionImportTemplate(): string {
  return [
    "registration_number,external_id,smiles,inchi_key,name,notes",
    "CC-000001,,,,,",
    ",ACME-LOT-42,,,,partner sample",
    ",,c1ccccc1O,,phenol,",
    "",
  ].join("\n");
}
