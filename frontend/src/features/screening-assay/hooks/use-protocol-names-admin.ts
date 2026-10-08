"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  FlaggedProtocolResponse,
  RederiveRequest,
  RederiveResponse,
} from "@/shared/lib/api/model";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PROTOCOLS_KEY } from "./query-keys";

const FLAGS_KEY = ["protocol-names", "flags"];

/** Protocols whose generated name needs attention (one row per code). */
export function useNameFlags() {
  return useQuery({
    queryKey: FLAGS_KEY,
    queryFn: () =>
      customInstance<FlaggedProtocolResponse[]>({
        url: `${API_V1}/protocol-names/flags`,
        method: "GET",
      }),
  });
}

/** Dry run lists what would change; apply renames and refreshes protocols and flags. */
export function useRederiveNames() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: RederiveRequest) =>
      customInstance<RederiveResponse>({
        url: `${API_V1}/protocol-names/rederive`,
        method: "POST",
        data,
      }),
    onSuccess: (result, variables) => {
      if (variables.dry_run) return;
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      qc.invalidateQueries({ queryKey: FLAGS_KEY });
      const r = result.report;
      if (r) {
        showSuccess(
          `${r.renamed} renamed, ${r.flagged} flagged${r.failed.length ? `, ${r.failed.length} failed` : ""}`,
        );
      }
    },
    onError: (err: Error) => showError(err.message),
  });
}
