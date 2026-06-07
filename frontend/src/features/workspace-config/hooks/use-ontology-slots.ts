"use client";

import { createCrudHooks } from "@/shared/hooks/create-crud-hooks";
import { API_V1 } from "@/shared/lib/api/custom-instance";
import type {
  CreateOntologySlotBody,
  OntologySlotResponse,
  UpdateOntologySlotBody,
} from "@/shared/lib/api/model";

// Aliases of the orval-generated DTOs (source of truth).
export type OntologySlotDefinition = OntologySlotResponse;
export type CreateOntologySlotInput = CreateOntologySlotBody;
export type UpdateOntologySlotInput = UpdateOntologySlotBody;

const slotHooks = createCrudHooks<
  OntologySlotDefinition,
  CreateOntologySlotInput,
  UpdateOntologySlotInput
>({
  entityName: "Ontology slot",
  baseUrl: `${API_V1}/ontology-slots`,
  queryKey: ["ontology-slots"],
});

export const useOntologySlots = slotHooks.useList;
export const useCreateOntologySlot = slotHooks.useCreate;
export const useUpdateOntologySlot = slotHooks.useUpdate;
export const useDeleteOntologySlot = slotHooks.useDelete;
