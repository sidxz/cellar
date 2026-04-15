"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import type {
  DisclosureOutcome,
  DisclosureRequest,
  MergeEventResponse,
  MergeImpact,
  MergeInput,
  SubmitDisclosureInput,
} from "../types/disclosure";

const DISCLOSURES_KEY = ["disclosures"];
const MOLECULES_KEY = ["molecules"];

export function useDisclosures(status?: string) {
  return useQuery({
    queryKey: [...DISCLOSURES_KEY, { status }],
    queryFn: () =>
      customInstance<DisclosureRequest[]>({
        url: "/api/v1/disclosures",
        method: "GET",
        params: status ? { status } : undefined,
      }),
  });
}

export function useConflictDisclosures() {
  return useDisclosures("conflict");
}

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
      showSuccess("Disclosure submitted");
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
      showSuccess("Compounds merged");
    },
  });
}

export function useResolveDisclosureConflict(disclosureId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { resolution: string; reason?: string }) =>
      customInstance<DisclosureRequest>({
        url: `/api/v1/disclosures/${disclosureId}/resolve`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: DISCLOSURES_KEY });
      qc.invalidateQueries({ queryKey: MOLECULES_KEY });
      showSuccess("Conflict resolved");
    },
  });
}

export function useMergeHistory(moleculeId: string | undefined) {
  return useQuery({
    queryKey: ["merge-history", moleculeId],
    queryFn: () =>
      customInstance<MergeEventResponse[]>({
        url: `/api/v1/molecules/${moleculeId}/merge-history`,
        method: "GET",
      }),
    enabled: !!moleculeId,
  });
}

export function usePendingDisclosures() {
  return useDisclosures("pending_confirmation");
}

export function useConfirmDisclosure(disclosureId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      customInstance<DisclosureOutcome>({
        url: `/api/v1/disclosures/${disclosureId}/confirm`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: DISCLOSURES_KEY });
      qc.invalidateQueries({ queryKey: MOLECULES_KEY });
      showSuccess("Disclosure confirmed — compounds merged");
    },
  });
}

export function useRejectDisclosure(disclosureId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { reason?: string }) =>
      customInstance<DisclosureRequest>({
        url: `/api/v1/disclosures/${disclosureId}/reject`,
        method: "POST",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: DISCLOSURES_KEY });
      qc.invalidateQueries({ queryKey: MOLECULES_KEY });
      showSuccess("Disclosure rejected");
    },
  });
}

export function useMergeImpact(
  sourceId: string | undefined,
  targetId: string | undefined
) {
  return useQuery({
    queryKey: ["merge-impact", sourceId, targetId],
    queryFn: () =>
      customInstance<MergeImpact>({
        url: `/api/v1/molecules/${sourceId}/merge-impact/${targetId}`,
        method: "GET",
      }),
    enabled: !!sourceId && !!targetId,
  });
}
