import Papa from "papaparse";

export type ParsedCsv =
  | { kind: "ok"; headers: string[]; rows: Record<string, string>[] }
  | { kind: "error"; message: string };

export async function parseCollectionImportFile(
  input: File,
): Promise<ParsedCsv> {
  const ext = input.name.toLowerCase().split(".").pop();
  if (ext === "xlsx" || ext === "xls") {
    return parseExcel(input);
  }
  return parseCsv(input);
}

/**
 * Backward-compatible alias. Accepts both `File` (production) and `string`
 * (tests + the original API). Delegates to `parseCsv` for the string path.
 */
export async function parseCollectionImportCsv(
  input: string | File,
): Promise<ParsedCsv> {
  if (typeof input !== "string" && (input as File).name) {
    return parseCollectionImportFile(input as File);
  }
  return parseCsv(input);
}

async function parseCsv(input: string | File): Promise<ParsedCsv> {
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

async function parseExcel(file: File): Promise<ParsedCsv> {
  const ExcelJS = await import("exceljs");
  // `File.arrayBuffer()` is missing in jsdom; fall back to `Response` (works in
  // both real browsers and jsdom/node).
  const buffer =
    typeof file.arrayBuffer === "function"
      ? await file.arrayBuffer()
      : await new Response(file).arrayBuffer();
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(buffer);
  const sheet = workbook.worksheets[0];
  if (!sheet) {
    return { kind: "error", message: "Workbook contains no sheets" };
  }
  // Read row 1 as headers
  const headerRow = sheet.getRow(1);
  const headers: string[] = [];
  headerRow.eachCell({ includeEmpty: false }, (cell) => {
    headers.push(String(cell.value ?? "").trim());
  });
  if (headers.length === 0) {
    return { kind: "error", message: "no headers detected" };
  }
  // Read remaining rows
  const rows: Record<string, string>[] = [];
  sheet.eachRow({ includeEmpty: false }, (row, rowNumber) => {
    if (rowNumber === 1) return;
    const obj: Record<string, string> = {};
    headers.forEach((h, idx) => {
      // exceljs is 1-indexed
      const cell = row.getCell(idx + 1);
      obj[h] = String(cell.value ?? "").trim();
    });
    // Skip rows where every value is empty
    if (Object.values(obj).every((v) => v === "")) return;
    rows.push(obj);
  });
  return { kind: "ok", headers, rows };
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
