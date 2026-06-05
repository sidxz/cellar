import Papa from "papaparse";
import type { BulkIdentifierRowBody } from "../types";

export interface ParseResult {
  rows: BulkIdentifierRowBody[];
  errors: string[];
}

const REQUIRED_COLUMNS = ["external_identifier"];
const OPTIONAL_COLUMNS = [
  "cellar_batch_number",
  "cellar_molecule_reg_number",
  "cellar_batch_sequence",
  "identifier_type",
  "source",
];
const ALL_COLUMNS = [...REQUIRED_COLUMNS, ...OPTIONAL_COLUMNS];

export async function parseBulkIdentifierCsv(file: File): Promise<ParseResult> {
  return new Promise((resolve) => {
    const errors: string[] = [];
    const rows: BulkIdentifierRowBody[] = [];

    Papa.parse<Record<string, string>>(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const headers = results.meta.fields ?? [];
        const missingRequired = REQUIRED_COLUMNS.filter((c) => !headers.includes(c));
        if (missingRequired.length) {
          errors.push(`Missing required column(s): ${missingRequired.join(", ")}`);
        }
        const unknownColumns = headers.filter((h) => !ALL_COLUMNS.includes(h));
        if (unknownColumns.length) {
          errors.push(`Unknown column(s) (ignored): ${unknownColumns.join(", ")}`);
        }

        results.data.forEach((raw, idx) => {
          const external = (raw.external_identifier ?? "").trim();
          if (!external) {
            errors.push(`Row ${idx + 1}: external_identifier is empty`);
            return;
          }
          const batchNumber = (raw.cellar_batch_number ?? "").trim() || null;
          const molReg = (raw.cellar_molecule_reg_number ?? "").trim() || null;
          const seqRaw = (raw.cellar_batch_sequence ?? "").trim();
          const seq = seqRaw ? Number.parseInt(seqRaw, 10) : null;
          if (seqRaw && Number.isNaN(seq!)) {
            errors.push(`Row ${idx + 1}: cellar_batch_sequence "${seqRaw}" is not an integer`);
            return;
          }
          rows.push({
            row_index: idx,
            cellar_batch_number: batchNumber,
            cellar_molecule_reg_number: molReg,
            cellar_batch_sequence: seq,
            external_identifier: external,
            identifier_type: (raw.identifier_type ?? "").trim() || "external_lot",
            source: (raw.source ?? "").trim() || null,
          });
        });

        resolve({ rows, errors });
      },
      error: (err) => {
        errors.push(`CSV parse error: ${err.message}`);
        resolve({ rows: [], errors });
      },
    });
  });
}

export function generateCsvTemplate(): string {
  const header =
    "cellar_batch_number,cellar_molecule_reg_number,cellar_batch_sequence,external_identifier,identifier_type,source";
  const examples = [
    "CC-000001-001,,,SACC-0001-001,external_lot,",
    ",CC-000002,1,SACC-0002-A,external_lot,",
  ];
  return `${[header, ...examples].join("\n")}\n`;
}
