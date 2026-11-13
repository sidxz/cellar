"use client";

import { useMutation } from "@tanstack/react-query";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { LayoutFile } from "../types";

/** Read a labelling layout file and resolve its compounds and batches. Writes nothing.
 *  POST /api/v1/runs/{runId}/resolve-layout-file (multipart: file). */
export function useResolveLayoutFile(runId: string) {
  return useMutation({
    mutationFn: async ({ file }: { file: File }) => {
      const formData = new FormData();
      formData.append("file", file);
      return customInstance<LayoutFile>({
        url: `${API_V1}/runs/${runId}/resolve-layout-file`,
        method: "POST",
        data: formData,
      });
    },
  });
}
