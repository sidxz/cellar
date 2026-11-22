"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { ChangeDiscloserBody } from "@/shared/lib/api/model";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Molecule } from "../types";
import { MOLECULES_KEY } from "./query-keys";

/** Correct who disclosed a compound and for which Duar org (an admin or its registrant). */
export function useChangeDiscloser(moleculeId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ChangeDiscloserBody) =>
      customInstance<Molecule>({
        url: `${API_V1}/molecules/${moleculeId}/discloser`,
        method: "PUT",
        data,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: MOLECULES_KEY });
      qc.invalidateQueries({ queryKey: ["audit"] });
      showSuccess("Discloser saved");
    },
    onError: (err: Error) => showError(err.message || "Could not save the discloser"),
  });
}
