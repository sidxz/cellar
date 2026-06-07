import type {
  CreateOrganizationBody,
  CreateVocabularyBody,
  OrganizationResponse,
  OrganizationType as OrganizationTypeModel,
  UpdateOrganizationBody,
  UpdateVocabularyBody,
  VocabularyResponse,
  WorkspaceSettingsResponse,
} from "@/shared/lib/api/model";

// Alias of the orval-generated enum (source of truth) so the union can't drift.
export type OrganizationType = OrganizationTypeModel;

export const ORG_TYPE_LABELS: Record<OrganizationType, string> = {
  internal: "Internal",
  pharma_partner: "Pharma Partner",
  cro: "CRO",
  academic: "Academic",
  vendor: "Vendor",
  government: "Government",
};

// Aliases of the orval-generated DTOs (source of truth).
export type Organization = OrganizationResponse;
export type CreateOrganizationInput = CreateOrganizationBody;
export type UpdateOrganizationInput = UpdateOrganizationBody;

// CLIENT-SIDE working types — NOT backend DTOs. The backend types
// `audit_reason_policy` as a bare `str`, and `registration_rules` /
// `custom_field_definitions` as opaque `dict` / `list` on WorkspaceSettingsResponse.
// These narrowed/structured shapes are the FE's interpretation, used by the
// settings form; they are narrowed from the generated opaque payload at the
// consumption edge.
export type AuditReasonPolicy = "always" | "never" | "configurable";

export interface CustomFieldDefinition {
  name: string;
  label: string;
  data_type: "text" | "number" | "date" | "select";
  required: boolean;
  vocabulary_name?: string | null;
}

export interface RegistrationRules {
  create_batch_on_duplicate?: boolean;
  registration_number_prefix?: string;
  registration_number_width?: number;
  batch_sequence_width?: number;
}

// Alias of the orval-generated DTO (source of truth). `registration_rules` and
// `custom_field_definitions` resolve to the generated opaque payload types; the
// settings form narrows them to RegistrationRules / CustomFieldDefinition[] at
// the consumption edge.
export type WorkspaceSettings = WorkspaceSettingsResponse;

// Alias of the orval-generated DTO (source of truth).
export type Vocabulary = VocabularyResponse;
export type CreateVocabularyInput = CreateVocabularyBody;
export type UpdateVocabularyInput = UpdateVocabularyBody;
