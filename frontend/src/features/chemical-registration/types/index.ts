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

/** The molecule response, with the string fields the app treats as unions narrowed. */
export type Molecule = Omit<
  import("@/shared/lib/api/model").MoleculeResponse,
  | "molecule_type"
  | "structure"
  | "descriptors"
  | "structure_status"
  | "lifecycle_stage"
  | "molecular_formula"
  | "stereochemistry"
  | "invention_date"
  | "disclosed_at"
  | "merged_into_id"
  | "custom_fields"
  | "identifiers"
> & {
  molecule_type: MoleculeType;
  structure: MoleculeStructure | null;
  descriptors: MoleculeDescriptors | null;
  molecular_formula: string | null;
  structure_status: StructureStatus;
  lifecycle_stage: LifecycleStage;
  stereochemistry: string | null;
  invention_date: string | null;
  disclosed_at: string | null;
  merged_into_id: string | null;
  custom_fields: Record<string, unknown> | null;
  identifiers: MoleculeIdentifier[];
};

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

// Backend DTO — aliased from the orval-generated model (source of truth).
export type RegisterMoleculeInput = import("@/shared/lib/api/model").RegisterMoleculeBody;

export interface UpdateMoleculeInput {
  lifecycle_stage?: string;
  lifecycle_reason?: string;
  custom_fields?: Record<string, unknown> | null;
}
