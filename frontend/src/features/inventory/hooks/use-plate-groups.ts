"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  CreatePlateGroupBody,
  GroupTreeNodeResponse,
  GroupTreeResponse,
  PlateGroupDetailResponse,
  PlateGroupResponse,
  UpdatePlateGroupBody,
} from "@/shared/lib/api/model";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PLATES_KEY, PLATE_GROUPS_KEY } from "./query-keys";

export type PlateGroup = PlateGroupResponse;
export type PlateGroupTree = GroupTreeResponse;
export type PlateGroupNode = GroupTreeNodeResponse;
export type PlateGroupDetail = PlateGroupDetailResponse;

export function usePlateGroupTree(orgId?: string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: [...PLATE_GROUPS_KEY, "tree", orgId ?? "mine"],
    queryFn: ({ signal }) =>
      customInstance<PlateGroupTree>({
        url: `${API_V1}/plate-groups/tree`,
        method: "GET",
        params: orgId ? { org_id: orgId } : {},
        signal,
      }),
    enabled: opts?.enabled ?? true,
  });
}

export function usePlateGroup(groupId: string | undefined) {
  return useQuery({
    queryKey: [...PLATE_GROUPS_KEY, "detail", groupId],
    queryFn: ({ signal }) =>
      customInstance<PlateGroupDetail>({
        url: `${API_V1}/plate-groups/${groupId}`,
        method: "GET",
        signal,
      }),
    enabled: !!groupId,
  });
}

function useGroupMutation<TVars>(
  request: (vars: TVars) => Parameters<typeof customInstance>[0],
  successMessage: string,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: TVars) => customInstance<unknown>(request(vars)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PLATE_GROUPS_KEY });
      qc.invalidateQueries({ queryKey: PLATES_KEY });
      showSuccess(successMessage);
    },
    // Errors toast via the global MutationCache handler.
  });
}

export function useCreatePlateGroup() {
  return useGroupMutation(
    (body: CreatePlateGroupBody) => ({
      url: `${API_V1}/plate-groups`,
      method: "POST" as const,
      data: body,
    }),
    "Group created",
  );
}

export function useUpdatePlateGroup() {
  return useGroupMutation(
    ({ groupId, ...body }: UpdatePlateGroupBody & { groupId: string }) => ({
      url: `${API_V1}/plate-groups/${groupId}`,
      method: "PATCH" as const,
      data: body,
    }),
    "Group updated",
  );
}

export function useMovePlateGroup() {
  return useGroupMutation(
    ({ groupId, parentGroupId }: { groupId: string; parentGroupId: string | null }) => ({
      url: `${API_V1}/plate-groups/${groupId}/move`,
      method: "POST" as const,
      data: { parent_group_id: parentGroupId },
    }),
    "Group moved",
  );
}

export function useDeletePlateGroup() {
  return useGroupMutation(
    ({ groupId }: { groupId: string }) => ({
      url: `${API_V1}/plate-groups/${groupId}`,
      method: "DELETE" as const,
    }),
    "Group deleted",
  );
}

export function useAssignPlatesToGroup() {
  return useGroupMutation(
    ({ groupId, plateIds }: { groupId: string; plateIds: string[] }) => ({
      url: `${API_V1}/plate-groups/${groupId}/plates`,
      method: "POST" as const,
      data: { plate_ids: plateIds },
    }),
    "Plates assigned",
  );
}

export function useRemovePlatesFromGroup() {
  return useGroupMutation(
    ({ groupId, plateIds }: { groupId: string; plateIds: string[] }) => ({
      url: `${API_V1}/plate-groups/${groupId}/plates`,
      method: "DELETE" as const,
      data: { plate_ids: plateIds },
    }),
    "Plates removed from group",
  );
}
