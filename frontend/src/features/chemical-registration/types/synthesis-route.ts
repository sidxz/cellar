export type RouteType = "linear" | "convergent" | "divergent";

export const ROUTE_TYPE_LABELS: Record<RouteType, string> = {
  linear: "Linear",
  convergent: "Convergent",
  divergent: "Divergent",
};

export type RouteStatus = "draft" | "validated" | "preferred" | "deprecated";

export const ROUTE_STATUS_LABELS: Record<RouteStatus, string> = {
  draft: "Draft",
  validated: "Validated",
  preferred: "Preferred",
  deprecated: "Deprecated",
};

export type RouteScale =
  | "milligram"
  | "gram"
  | "kilogram"
  | "pilot"
  | "production";

export const ROUTE_SCALE_LABELS: Record<RouteScale, string> = {
  milligram: "Milligram",
  gram: "Gram",
  kilogram: "Kilogram",
  pilot: "Pilot",
  production: "Production",
};

export interface ReactionReagent {
  role: string;
  molecule_id: string | null;
  name: string;
  cas_number: string | null;
  catalog_number: string | null;
  supplier: string | null;
  equivalents: number | null;
}

export interface ReactionStep {
  id: string;
  step_number: number;
  branch_label: string | null;
  name: string | null;
  named_reaction: string | null;
  reaction_smiles: string | null;
  product_molecule_id: string | null;
  product_description: string | null;
  conditions: Record<string, unknown> | null;
  outcome: Record<string, unknown> | null;
  reagents: ReactionReagent[];
  preceding_step_ids: string[];
  eln_entry_id: string | null;
  batch_id: string | null;
  notes: string | null;
}

export interface SynthesisRoute {
  id: string;
  workspace_id: string;
  target_molecule_id: string;
  name: string;
  description: string | null;
  route_type: RouteType;
  status: RouteStatus;
  total_steps: number;
  overall_yield: number | null;
  scale: RouteScale | null;
  source: string;
  source_reference: string | null;
  created_by: string;
  steps: ReactionStep[];
}

export interface SynthesisRouteSummary {
  id: string;
  workspace_id: string;
  target_molecule_id: string;
  name: string;
  route_type: RouteType;
  status: RouteStatus;
  total_steps: number;
  overall_yield: number | null;
  scale: RouteScale | null;
  source: string;
}

export interface CreateSynthesisRouteInput {
  target_molecule_id: string;
  name: string;
  description?: string | null;
  route_type?: string;
  scale?: string | null;
  source?: string;
  source_reference?: string | null;
}

export interface AddReactionStepInput {
  step_number: number;
  branch_label?: string | null;
  name?: string | null;
  named_reaction?: string | null;
  reaction_smiles?: string | null;
  reaction_smarts?: string | null;
  product_molecule_id?: string | null;
  product_description?: string | null;
  conditions?: Record<string, unknown> | null;
  reagents?: Array<Record<string, unknown>>;
  preceding_step_ids?: string[];
  notes?: string | null;
}

export interface RecordStepOutcomeInput {
  yield_percent?: number | null;
  crude_yield_percent?: number | null;
  purity_percent?: number | null;
  purification_method?: string | null;
  batch_id?: string | null;
}
