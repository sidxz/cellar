"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { customInstance } from "@/shared/lib/api/custom-instance";
import type {
  SummaryHeaderSuggestionModel,
  SummaryImportErrorModel,
  SummaryImportResponse,
  SummaryPreviewResponse,
} from "@/shared/lib/api/model";

// ─── Backend DTOs (orval-generated; re-exported under domain names) ──────────────
// NEVER redefine these shapes by hand — they mirror the backend response models
// and are kept in sync by `pnpm generate:api`.
export type {
  SummaryHeaderSuggestionModel,
  SummaryImportErrorModel,
  SummaryImportResponse,
  SummaryPreviewResponse,
};

// ─── FE-local types (NOT backend DTOs) ───────────────────────────────────────────
// These describe the request payload the wizard *builds* client-side. The import
// endpoint receives the mapping as a JSON-stringified `mapping` FormData field, so
// orval does not emit a model for it — we own this shape on the FE.

export type SummaryRole = "compound_ref" | "batch_ref" | "readout" | "ignore";

export interface SummaryColumnMapping {
  compound_ref?: string | null;
  batch_ref?: string | null;
  /** Map of source-header -> readout_definition_id for each readout column. */
  readout_columns: Record<string, string>;
}

// ─── Hooks ───────────────────────────────────────────────────────────────────────

/** Parse a wide-format summary file and suggest a per-column role mapping.
 *  POST /api/v1/runs/{runId}/preview-summary-file (multipart: file). */
export function usePreviewSummaryFile(runId: string) {
  return useMutation({
    mutationFn: async ({ file }: { file: File }) => {
      const formData = new FormData();
      formData.append("file", file);
      return customInstance<SummaryPreviewResponse>({
        url: `/api/v1/runs/${runId}/preview-summary-file`,
        method: "POST",
        data: formData,
      });
    },
  });
}

/** Commit wide-format summary values for a run (upsert, well-less).
 *  POST /api/v1/runs/{runId}/import-summary-file
 *  (multipart: file + mapping = JSON.stringify(SummaryColumnMapping)). */
export function useImportSummaryFile(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      file,
      mapping,
    }: {
      file: File;
      mapping: SummaryColumnMapping;
    }) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("mapping", JSON.stringify(mapping));
      return customInstance<SummaryImportResponse>({
        url: `/api/v1/runs/${runId}/import-summary-file`,
        method: "POST",
        data: formData,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["readout-data"] });
      qc.invalidateQueries({ queryKey: ["dose-response-curves"] });
      qc.invalidateQueries({ queryKey: ["runs"] });
      qc.invalidateQueries({ queryKey: ["run", runId] });
    },
  });
}
