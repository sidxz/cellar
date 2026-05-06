"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { customInstance } from "@/shared/lib/api/custom-instance";

// ─── Types ─────────────────────────────────────────────────────────────────────

export type ImportRole =
  | "well"
  | "plate_name"
  | "concentration"
  | "batch_ref"
  | "readout";

export type ImportConfidence = "high" | "medium" | "low";

export interface HeaderSuggestion {
  header: string;
  role: ImportRole | null;
  confidence: ImportConfidence;
  reason: string;
}

export interface PlatePreview {
  plate_name: string;
  plate_format: string;
  well_count: number;
  sample_count: number;
  blank_count: number;
}

export interface WellConflict {
  plate_name: string;
  well_position: string;
  reason: string;
}

export interface ReadoutConflict {
  plate_name: string;
  well_position: string;
  readout_definition_id: string;
  readout_name: string;
}

export interface PreviewRunFileResponse {
  preview_id: string;
  headers: string[];
  suggestions: HeaderSuggestion[];
  sample_rows: Array<Record<string, string>>;
  plates: PlatePreview[];
  matched_batches: number;
  unmatched_batches: string[];
  total_rows: number;
  expires_in_seconds: number;
  validation_errors: string[];
  will_create_plates: number;
  will_create_wells: number;
  will_create_readouts: number;
  will_skip_wells: WellConflict[];
  will_skip_readouts: ReadoutConflict[];
}

export interface ReadoutColumnPayload {
  header: string;
  readout_definition_id: string;
}

export interface ColumnMappingPayload {
  well: string;
  plate_name: string | null;
  concentration: string | null;
  batch_ref: string | null;
  readout_columns: ReadoutColumnPayload[];
}

export interface ImportRunFilePayload {
  preview_id: string;
  mapping: ColumnMappingPayload;
}

export interface ImportRunFileResponse {
  rows_total: number;
  plates_created: number;
  wells_created: number;
  readouts_created: number;
  unmatched_batches: string[];
  controls_from_template: number;
  controls_unclassified: number;
  skipped_rows: number;
  conflicts_well_metadata: WellConflict[];
  conflicts_readout: ReadoutConflict[];
  attachment_id: string | null;
  /** Non-fatal warning when post-import normalization fails (missing controls etc). */
  compute_warning: string | null;
  attachment_warning: string | null;
}

export interface RunImportTemplate {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  column_mapping: Record<string, unknown>;
  created_by: string;
  created_at: string;
  updated_at: string | null;
}

// ─── Hooks ─────────────────────────────────────────────────────────────────────

export function usePreviewRunFile(runId: string) {
  return useMutation({
    mutationFn: async ({ file }: { file: File }) => {
      const formData = new FormData();
      formData.append("file", file);
      return customInstance<PreviewRunFileResponse>({
        url: `/api/v1/runs/${runId}/preview-file`,
        method: "POST",
        data: formData,
      });
    },
  });
}

export function useImportRunFile(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: ImportRunFilePayload) =>
      customInstance<ImportRunFileResponse>({
        url: `/api/v1/runs/${runId}/import-file`,
        method: "POST",
        data: payload,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plate-map", runId] });
      qc.invalidateQueries({ queryKey: ["readout-data"] });
      qc.invalidateQueries({ queryKey: ["dose-response-curves"] });
      qc.invalidateQueries({ queryKey: ["runs"] });
      qc.invalidateQueries({ queryKey: ["attachments", "run", runId] });
    },
  });
}

export interface ResetRunDataResponse {
  plates_deleted: number;
  wells_deleted: number;
  readouts_deleted: number;
  curves_deleted: number;
}

export function useResetRunData(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      customInstance<ResetRunDataResponse>({
        url: `/api/v1/runs/${runId}/reset-data`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plate-map", runId] });
      qc.invalidateQueries({ queryKey: ["readout-data"] });
      qc.invalidateQueries({ queryKey: ["dose-response-curves"] });
      qc.invalidateQueries({ queryKey: ["runs"] });
      qc.invalidateQueries({ queryKey: ["run", runId] });
    },
  });
}

export function useRunImportTemplates() {
  return useQuery({
    queryKey: ["run-import-templates"],
    queryFn: () =>
      customInstance<RunImportTemplate[]>({
        url: `/api/v1/run-import-templates`,
        method: "GET",
      }),
  });
}

export function useCreateRunImportTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      name: string;
      description?: string;
      column_mapping: Record<string, unknown>;
    }) =>
      customInstance<RunImportTemplate>({
        url: `/api/v1/run-import-templates`,
        method: "POST",
        data: input,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["run-import-templates"] });
    },
  });
}
