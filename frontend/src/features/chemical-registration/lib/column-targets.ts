import type { ColumnMappingBody, ColumnTarget } from "@/shared/lib/api/model";

export const TARGET_LABELS: Record<ColumnTarget, string> = {
  name: "Compound name",
  smiles: "Structure (SMILES)",
  compound_id: "Compound ID",
  cas_number: "CAS number",
  chembl_id: "ChEMBL ID",
  pubchem_cid: "PubChem CID",
  vendor_id: "Vendor ID",
  molecule_type: "Molecule type",
  batch_id: "Batch ID",
  amount_value: "Amount",
  amount_unit: "Amount unit",
  salt_code: "Salt code",
  salt_stoichiometry: "Salt stoichiometry",
  purity: "Purity (%)",
  batch_source: "Synthesized or purchased",
  appearance: "Appearance",
  ignore: "Don't import",
};

export const TARGET_GROUPS: { label: string; targets: ColumnTarget[] }[] = [
  {
    label: "Compound",
    targets: [
      "name",
      "smiles",
      "compound_id",
      "cas_number",
      "chembl_id",
      "pubchem_cid",
      "vendor_id",
      "molecule_type",
    ],
  },
  {
    label: "Batch",
    targets: [
      "batch_id",
      "amount_value",
      "amount_unit",
      "salt_code",
      "salt_stoichiometry",
      "purity",
      "batch_source",
      "appearance",
    ],
  },
];

// Mirror LABELLED_TARGETS / MULTI_TARGETS in backend bulk_column_mapping.py
// (the server validates the mapping again).
const LABELLED = new Set<ColumnTarget>([
  "compound_id",
  "cas_number",
  "chembl_id",
  "pubchem_cid",
  "vendor_id",
  "batch_id",
]);
const MULTI = new Set<ColumnTarget>(["compound_id", "batch_id", "ignore"]);

export const isLabelled = (t: ColumnTarget) => LABELLED.has(t);
/** Only ID columns can hold several values in one cell. */
export const isSplittable = (t: ColumnTarget) => t === "compound_id" || t === "batch_id";
export const isMulti = (t: ColumnTarget) => MULTI.has(t);

type MappedColumn = ColumnMappingBody["columns"][number];

/** The sentence that blocks Preview, or null when the mapping can be previewed. */
export function mappingProblem(
  mapping: ColumnMappingBody,
  structureImplied: boolean,
): string | null {
  const owner = new Map<ColumnTarget, string>();
  for (const c of mapping.columns) {
    if (isLabelled(c.target) && !c.source?.trim()) return `Give "${c.header}" a Source.`;
    if (isMulti(c.target)) continue;
    const first = owner.get(c.target);
    if (first !== undefined) {
      return `"${first}" and "${c.header}" both go to ${TARGET_LABELS[c.target]}; only one column can.`;
    }
    owner.set(c.target, c.header);
  }
  const targets = new Set(mapping.columns.map((c) => c.target));
  if (!structureImplied && !targets.has("name") && !targets.has("smiles")) {
    return "Pick the column with the compound name or the structure.";
  }
  return null;
}

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "");

/** Share of a saved mapping's headers present in the file (normalised). */
export function scoreSavedMapping(saved: ColumnMappingBody, headers: string[]): number {
  const file = new Set(headers.map(norm));
  if (saved.columns.length === 0) return 0;
  return saved.columns.filter((c) => file.has(norm(c.header))).length / saved.columns.length;
}

export const SAVED_MAPPING_MIN_SCORE = 0.7;

/**
 * The file's columns as the saved mapping says, keeping the file's own header
 * spelling; headers the saved mapping doesn't know keep their suggestion.
 */
export function applySavedMapping(
  saved: ColumnMappingBody,
  suggestion: ColumnMappingBody,
): ColumnMappingBody {
  const byNorm = new Map(saved.columns.map((c) => [norm(c.header), c]));
  const columns = suggestion.columns.map((c) => {
    const s = byNorm.get(norm(c.header));
    return s
      ? {
          header: c.header,
          target: s.target,
          source: s.source ?? null,
          separator: s.separator ?? undefined,
        }
      : c;
  });
  return { columns: oneColumnPerTarget(columns, (c) => byNorm.has(norm(c.header))) };
}

/**
 * A single-valued target takes one column: the columns ``kept`` says keep claim theirs
 * first, then a suggestion for a target already taken becomes "Don't import".
 */
export function oneColumnPerTarget(
  columns: MappedColumn[],
  kept: (c: MappedColumn) => boolean,
): MappedColumn[] {
  const taken = new Set(columns.filter((c) => kept(c) && !isMulti(c.target)).map((c) => c.target));
  return columns.map((c) => {
    if (kept(c) || isMulti(c.target)) return c;
    if (taken.has(c.target)) return { header: c.header, target: "ignore", source: null };
    taken.add(c.target);
    return c;
  });
}
