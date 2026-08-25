"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { AddCommentBody, CommentResponse, CommentTarget } from "@/shared/lib/api/model";
import { showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { COMMENTS_KEY, LOANS_KEY } from "./query-keys";

export type Comment = CommentResponse;
export type CommentScope = { targetType: CommentTarget; targetId: string } | { loanId: string };

function scopeParams(scope: CommentScope): Record<string, string> {
  return "loanId" in scope
    ? { loan_id: scope.loanId }
    : { target_type: scope.targetType, target_id: scope.targetId };
}

export function useComments(scope: CommentScope, opts?: { enabled?: boolean }) {
  const params = scopeParams(scope);
  return useQuery({
    queryKey: [...COMMENTS_KEY, params],
    queryFn: ({ signal }) =>
      customInstance<Comment[]>({ url: `${API_V1}/comments`, method: "GET", params, signal }),
    enabled: opts?.enabled ?? true,
  });
}

export function useAddComment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AddCommentBody) =>
      customInstance<Comment>({ url: `${API_V1}/comments`, method: "POST", data: body }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: COMMENTS_KEY });
      qc.invalidateQueries({ queryKey: LOANS_KEY });
      showSuccess("Comment added");
    },
  });
}
