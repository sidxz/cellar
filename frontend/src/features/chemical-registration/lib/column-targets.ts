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
export const isMulti = (t: ColumnTarget) => MULTI.has(t);

/** The sentence that blocks Preview, or null when the mapping can be previewed. */
export function mappingProblem(
  mapping: ColumnMappingBody,
  structureImplied: boolean,
): string | null {
  for (const c of mapping.columns) {
    if (isLabelled(c.target) && !c.source?.trim()) return `Give "${c.header}" a Source.`;
  }
  const targets = new Set(mapping.columns.map((c) => c.target));
  if (!structureImplied && !targets.has("name") && !targets.has("smiles")) {
    return "Pick the column with the compound name or the structure.";
  }
  return null;
}
