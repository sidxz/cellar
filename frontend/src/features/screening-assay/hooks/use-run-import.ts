"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { customInstance } from "@/shared/lib/api/custom-instance";
import { showWarning } from "@/shared/lib/toast";

/** Compose a non-blocking warning toast body from a fit_warnings array.
 *  Up to 3 lines are shown verbatim; anything beyond is collapsed into a
 *  "+N more" suffix so the toast doesn't grow unbounded on bad runs. */
function buildFitWarningDescription(warnings: string[]): string {
  const head = warnings.slice(0, 3);
  const rest = warnings.length - head.length;
  return rest > 0 ? `${head.join("\n")}\n+${rest} more` : head.join("\n");
}

// ─── Types ─────────────────────────────────────────────────────────────────────

export type ImportRole =
  | "well"
  | "plate_name"
  | "concentration"
  | "batch_ref"
  | "compound_ref"
  | "readout";

export type ImportConfidence = "high" | "medium" | "low";

export interface HeaderSuggestion {
  header: string;
  role: ImportRole | null;
  confidence: ImportConfidence;
  reason: string;
  /** Set by the backend when the header's normalized name matches a
   *  protocol-defined readout (numeric or text). The wizard pre-binds
   *  the readout-def select from this id. */
  readout_definition_id?: string | null;
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

export interface BatchOption {
  batch_id: string;
  batch_number: string;
  salt_form: string | null;
  purity: number | null;
  /** ISO-8601 timestamp from the BE serializer. */
  created_at: string;
}

export interface AmbiguousCompound {
  compound_ref: string;
  molecule_id: string;
  molecule_name: string;
  batch_options: BatchOption[];
  affected_row_count: number;
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
  matched_compounds: number;
  unmatched_compound_refs: string[];
  ambiguous_compounds: AmbiguousCompound[];
  /** Pre-formatted "Plate-1 A12: <reason>" strings for direct render. */
  row_conflicts: string[];
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
  compound_ref: string | null;
  readout_columns: ReadoutColumnPayload[];
}

export interface CompoundBatchOverride {
  molecule_id: string;
  batch_id: string;
}

export interface ImportRunFilePayload {
  preview_id: string;
  mapping: ColumnMappingPayload;
  compound_batch_overrides: CompoundBatchOverride[];
  /** When true, auto-create placeholder batches for unmatched batch refs
   *  whose compound resolves to a known molecule. Default false. */
  auto_create_unmatched_batches?: boolean;
}

export interface ImportRunFileResponse {
  rows_total: number;
  plates_created: number;
  wells_created: number;
  readouts_created: number;
  unmatched_batches: string[];
  unmatched_compound_refs: string[];
  controls_from_template: number;
  controls_unclassified: number;
  skipped_rows: number;
  conflicts_well_metadata: WellConflict[];
  conflicts_readout: ReadoutConflict[];
  attachment_id: string | null;
  /** Non-fatal warning when post-import normalization fails (missing controls etc). */
  compute_warning: string | null;
  attachment_warning: string | null;
  /** Per-compound fit failure messages from the post-import curve fit. Optional
   *  for back-compat with deployments that haven't been upgraded. */
  fit_warnings?: string[];
  /** Number of placeholder batches auto-created during this import.
   *  Always 0 (or absent on older deployments) when
   *  auto_create_unmatched_batches was false on the request. */
  auto_created_batches?: number;
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

export interface RepreviewRunFilePayload {
  preview_id: string;
  mapping: ColumnMappingPayload;
}

export function useRepreviewRunFile(runId: string) {
  return useMutation({
    mutationFn: async (payload: RepreviewRunFilePayload) =>
      customInstance<PreviewRunFileResponse>({
        url: `/api/v1/runs/${runId}/repreview-file`,
        method: "POST",
        data: payload,
      }),
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
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["plate-map", runId] });
      qc.invalidateQueries({ queryKey: ["readout-data"] });
      qc.invalidateQueries({ queryKey: ["dose-response-curves"] });
      qc.invalidateQueries({ queryKey: ["runs"] });
      qc.invalidateQueries({ queryKey: ["attachments", "run", runId] });
      const warnings = data.fit_warnings ?? [];
      if (warnings.length > 0) {
        showWarning(`Run imported. ${warnings.length} curve(s) had fit issues.`, {
          description: buildFitWarningDescription(warnings),
        });
      }
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
        url: "/api/v1/run-import-templates",
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
        url: "/api/v1/run-import-templates",
        method: "POST",
        data: input,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["run-import-templates"] });
    },
  });
}
