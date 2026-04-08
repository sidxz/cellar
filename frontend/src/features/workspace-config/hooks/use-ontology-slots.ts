"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";

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

const ONTOLOGY_SLOTS_KEY = ["ontology-slots"];

export function useOntologySlots() {
  return useQuery({
    queryKey: ONTOLOGY_SLOTS_KEY,
    queryFn: () =>
      customInstance<OntologySlotDefinition[]>({
        url: "/api/v1/ontology-slots",
        method: "GET",
      }),
  });
}

export function useCreateOntologySlot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateOntologySlotInput) =>
      customInstance<OntologySlotDefinition>({
        url: "/api/v1/ontology-slots",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ONTOLOGY_SLOTS_KEY });
      showSuccess("Ontology slot created");
    },
  });
}

export function useUpdateOntologySlot(slotId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateOntologySlotInput) =>
      customInstance<OntologySlotDefinition>({
        url: `/api/v1/ontology-slots/${slotId}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ONTOLOGY_SLOTS_KEY });
      showSuccess("Ontology slot updated");
    },
  });
}

export function useDeleteOntologySlot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slotId: string) =>
      customInstance<void>({
        url: `/api/v1/ontology-slots/${slotId}`,
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ONTOLOGY_SLOTS_KEY });
      showSuccess("Ontology slot deleted");
    },
  });
}
