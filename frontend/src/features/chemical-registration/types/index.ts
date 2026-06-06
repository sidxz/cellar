export type MoleculeType =
  | "small_molecule"
  | "peptide"
  | "biologic"
  | "antibody"
  | "nucleic_acid"
  | "mixture"
  | "unknown";

export const MOLECULE_TYPE_LABELS: Record<MoleculeType, string> = {
  small_molecule: "Small Molecule",
  peptide: "Peptide",
  biologic: "Biologic",
  antibody: "Antibody",
  nucleic_acid: "Nucleic Acid",
  mixture: "Mixture",
  unknown: "Unknown",
};

export type LifecycleStage =
  | "registered"
  | "active"
  | "hit"
  | "lead"
  | "preclinical_candidate"
  | "development_candidate"
  | "deprioritized"
  | "archived";

export const LIFECYCLE_LABELS: Record<LifecycleStage, string> = {
  registered: "Registered",
  active: "Active",
  hit: "Hit",
  lead: "Lead",
  preclinical_candidate: "Preclinical Candidate",
  development_candidate: "Development Candidate",
  deprioritized: "Deprioritized",
  archived: "Archived",
};

export type StructureStatus = "undisclosed" | "disclosed";

export interface MoleculeStructure {
  smiles: string | null;
  cxsmiles: string | null;
  inchi: string | null;
  inchi_key: string | null;
}

export interface MoleculeDescriptors {
  molecular_formula: string | null;
  molecular_weight: number | null;
  exact_mass: number | null;
  logp: number | null;
  tpsa: number | null;
  hbd: number | null;
  hba: number | null;
  rotatable_bonds: number | null;
  aromatic_rings: number | null;
  ring_count: number | null;
  heavy_atom_count: number | null;
  ro5_violations: number | null;
}

export interface MoleculeIdentifier {
  id: string;
  identifier: string;
  identifier_type: string;
  source: string;
  registered_by: string;
}

export interface Molecule {
  id: string;
  workspace_id: string;
  registration_number: string;
  name: string;
  molecule_type: MoleculeType;
  structure: MoleculeStructure | null;
  descriptors: MoleculeDescriptors | null;
  molecular_formula: string | null;
  structure_status: StructureStatus;
  registration_status: string;
  synthesis_status: string;
  lifecycle_stage: LifecycleStage;
  stereochemistry: string | null;
  invention_date: string | null;
  disclosed_at: string | null;
  merged_into_id: string | null;
  custom_fields: Record<string, unknown> | null;
  originating_org_id: string;
  identifiers: MoleculeIdentifier[];
  version: number;
  // Set by /api/v1/search/execute on similarity-search rows; null/absent
  // for substructure/exact/property-only searches.
  similarity_score?: number | null;
}

export interface BatchInput {
  source: string;
  amount_value: number;
  amount_unit: string;
  salt_entry_id?: string | null;
  salt_name?: string | null;
  salt_smiles?: string | null;
  salt_stoichiometry?: number;
  formula_weight?: number | null;
  purity?: number | null;
  supplier_org_id?: string | null;
  appearance?: string | null;
}

// Backend DTO — aliased from the orval-generated model (source of truth).
export type RegistrationResponse = import("@/shared/lib/api/model").RegistrationResponse;

export interface RegisterMoleculeInput {
  name: string;
  smiles?: string | null;
  molecule_type?: string;
  external_ids?: { identifier: string; identifier_type: string }[];
  originating_org_id: string;
  custom_fields?: Record<string, unknown> | null;
  batch?: BatchInput | null;
  create_batch_on_duplicate?: boolean | null;
  auto_approve?: boolean;
}

export interface UpdateMoleculeInput {
  lifecycle_stage?: string;
  lifecycle_reason?: string;
  custom_fields?: Record<string, unknown> | null;
}
