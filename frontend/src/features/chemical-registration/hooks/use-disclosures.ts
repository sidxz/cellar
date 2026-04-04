"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import type {
  DisclosureOutcome,
  DisclosureRequest,
  MergeEventResponse,
  MergeInput,
  SubmitDisclosureInput,
} from "../types/disclosure";

const DISCLOSURES_KEY = ["disclosures"];
const MOLECULES_KEY = ["molecules"];

export function useDisclosuresForMolecule(moleculeId: string | undefined) {
  return useQuery({
    queryKey: [...DISCLOSURES_KEY, "by-molecule", moleculeId],
    queryFn: () =>
      customInstance<DisclosureRequest[]>({
        url: `/api/v1/disclosures/by-molecule/${moleculeId}`,
        method: "GET",
      }),
    enabled: !!moleculeId,
  });
}

export function useSubmitDisclosure() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: SubmitDisclosureInput) =>
      customInstance<DisclosureOutcome>({
        url: "/api/v1/disclosures",
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: DISCLOSURES_KEY });
      qc.invalidateQueries({ queryKey: MOLECULES_KEY });
    },
  });
}

export function useMergeMolecules(sourceMoleculeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: MergeInput) =>
      customInstance<MergeEventResponse>({
        url: `/api/v1/molecules/${sourceMoleculeId}/merge`,
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MOLECULES_KEY });
    },
  });
}
