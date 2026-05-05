"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { customInstance } from "@/shared/lib/api/custom-instance";

// ─── Types ─────────────────────────────────────────────────────────────────────

export type ImportRole =
  | "well"
  | "plate_name"
  | "concentration"
  | "batch_ref"
  | "scientist"
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
  scientist: string | null;
  readout_columns: ReadoutColumnPayload[];
}

export interface ImportRunFilePayload {
  preview_id: string;
  mapping: ColumnMappingPayload;
  concentration_unit: string;
  replace_existing: boolean;
}

export interface ImportRunFileResponse {
  rows_total: number;
  plates_created: number;
  wells_created: number;
  readouts_created: number;
  unmatched_batches: string[];
  controls_inferred: number;
  skipped_rows: number;
}

export interface RunImportTemplate {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  column_mapping: Record<string, unknown>;
  concentration_unit: string;
  created_by: string;
  created_at: string;
  updated_at: string | null;
}

// ─── Hooks ─────────────────────────────────────────────────────────────────────

export function usePreviewRunFile(runId: string) {
  return useMutation({
    mutationFn: async ({
      file,
      concentrationUnit = "uM",
    }: {
      file: File;
      concentrationUnit?: string;
    }) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("concentration_unit", concentrationUnit);
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
      concentration_unit?: string;
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
