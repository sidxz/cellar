"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";

export interface OntologySlotDefinition {
  id: string;
  workspace_id: string;
  name: string;
  label: string;
  ontology_sources: string[];
  root_concept_id: string | null;
  is_required: boolean;
  allow_free_text: boolean;
  display_order: number;
}

export interface CreateOntologySlotInput {
  name: string;
  label: string;
  ontology_sources: string[];
  root_concept_id?: string | null;
  is_required?: boolean;
  allow_free_text?: boolean;
  display_order?: number;
}

export interface UpdateOntologySlotInput {
  label?: string;
  ontology_sources?: string[];
  root_concept_id?: string | null;
  is_required?: boolean;
  allow_free_text?: boolean;
  display_order?: number;
}

const slotHooks = createCrudHooks<OntologySlotDefinition, CreateOntologySlotInput, UpdateOntologySlotInput>({
  entityName: "Ontology slot",
  baseUrl: "/api/v1/ontology-slots",
  queryKey: ["ontology-slots"],
});

export const useOntologySlots = slotHooks.useList;
export const useCreateOntologySlot = slotHooks.useCreate;
export const useUpdateOntologySlot = slotHooks.useUpdate;
export const useDeleteOntologySlot = slotHooks.useDelete;
