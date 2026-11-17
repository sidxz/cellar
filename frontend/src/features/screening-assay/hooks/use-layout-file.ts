"use client";

import { useMutation } from "@tanstack/react-query";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { ResolvePositionLabelsRequest } from "@/shared/lib/api/model";
import type { LayoutFile, PositionLabelMatches } from "../types";

/** The most labels the API reads in one request. */
const LABELS_PER_REQUEST = 500;

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

/** Read position labels as compound identifiers, the way a layout file's Compound column
 *  is read. Writes nothing. POST /api/v1/runs/{runId}/resolve-position-labels, as many
 *  requests as the labels need. */
export function useResolvePositionLabels(runId: string) {
  return useMutation({
    mutationFn: async ({ labels }: { labels: string[] }): Promise<PositionLabelMatches> => {
      const matches: PositionLabelMatches["matches"] = [];
      for (let i = 0; i < labels.length; i += LABELS_PER_REQUEST) {
        const body: ResolvePositionLabelsRequest = {
          labels: labels.slice(i, i + LABELS_PER_REQUEST),
        };
        const answer = await customInstance<PositionLabelMatches>({
          url: `${API_V1}/runs/${runId}/resolve-position-labels`,
          method: "POST",
          data: body,
        });
        matches.push(...answer.matches);
      }
      return { matches };
    },
  });
}
