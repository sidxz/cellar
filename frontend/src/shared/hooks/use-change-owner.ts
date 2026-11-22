"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useMutation, useQueryClient } from "@tanstack/react-query";

export type OwnedKind = "collections" | "projects" | "protocols";

/** Hand a collection, project or protocol to another Duar org (an admin or its creator). */
export function useChangeOwner(kind: OwnedKind, id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ownerOrgId: string) =>
      customInstance<unknown>({
        url: `${API_V1}/${kind}/${id}/owner`,
        method: "PUT",
        data: { owner_org_id: ownerOrgId },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [kind] });
      showSuccess("Owner saved");
    },
    onError: (err: Error) => showError(err.message || "Could not change the owner"),
  });
}

/** An admin, or the person who created it, may change who owns it. */
export function canChangeOwner(
  me: { user_id: string; is_admin: boolean; workspace_role: string } | undefined,
  createdBy: string | null | undefined,
): boolean {
  return !!me && me.workspace_role !== "viewer" && (me.is_admin || me.user_id === createdBy);
}
