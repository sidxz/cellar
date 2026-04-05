"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showSuccess } from "@/shared/lib/toast";
import type { CreateTargetInput, Target, UpdateTargetInput } from "../types";

const TARGETS_KEY = ["targets"];

export function useTargets() {
  return useQuery({
    queryKey: TARGETS_KEY,
    queryFn: () =>
      customInstance<Target[]>({
        url: "/api/v1/targets",
        method: "GET",
      }),
  });
}

export function useTarget(id: string | undefined) {
  return useQuery({
    queryKey: [...TARGETS_KEY, id],
    queryFn: () =>
      customInstance<Target>({
        url: `/api/v1/targets/${id}`,
        method: "GET",
      }),
    enabled: !!id,
  });
}

export function useCreateTarget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateTargetInput) =>
      customInstance<Target>({
        url: "/api/v1/targets",
        method: "POST",
        data,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: TARGETS_KEY }); showSuccess("Target created"); },
  });
}

export function useUpdateTarget(targetId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UpdateTargetInput) =>
      customInstance<Target>({
        url: `/api/v1/targets/${targetId}`,
        method: "PATCH",
        data,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: TARGETS_KEY }); showSuccess("Target updated"); },
  });
}

export function useDeleteTarget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (targetId: string) =>
      customInstance<void>({
        url: `/api/v1/targets/${targetId}`,
        method: "DELETE",
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: TARGETS_KEY }); showSuccess("Target deleted"); },
  });
}
