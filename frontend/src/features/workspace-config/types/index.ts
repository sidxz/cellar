export type OrganizationType =
  | "internal"
  | "pharma_partner"
  | "cro"
  | "academic"
  | "vendor"
  | "government";

export const ORG_TYPE_LABELS: Record<OrganizationType, string> = {
  internal: "Internal",
  pharma_partner: "Pharma Partner",
  cro: "CRO",
  academic: "Academic",
  vendor: "Vendor",
  government: "Government",
};

export interface Organization {
  id: string;
  workspace_id: string;
  name: string;
  org_type: OrganizationType;
  contact_name: string | null;
  contact_email: string | null;
  notes: string | null;
  is_active: boolean;
  version: number;
}

export interface CreateOrganizationInput {
  name: string;
  org_type: OrganizationType;
  contact_name?: string | null;
  contact_email?: string | null;
  notes?: string | null;
}

export interface UpdateOrganizationInput {
  name?: string;
  org_type?: OrganizationType;
  contact_name?: string | null;
  contact_email?: string | null;
  notes?: string | null;
}

export interface WorkspaceSettings {
  registration_rules: Record<string, unknown>;
  custom_field_definitions: Record<string, unknown>;
  default_molecule_type: string | null;
  audit_reason_policy: Record<string, unknown>;
  signature_required_for: string[];
  audit_retention_days: number | null;
  formulation_number_scheme: Record<string, unknown>;
  version: number;
}

export interface Vocabulary {
  id: string;
  workspace_id: string;
  name: string;
  terms: string[];
  is_locked: boolean;
  created_by: string;
  version: number;
}

export interface CreateVocabularyInput {
  name: string;
  terms?: string[];
}

export interface UpdateVocabularyInput {
  name?: string;
  terms?: string[];
  is_locked?: boolean;
}
