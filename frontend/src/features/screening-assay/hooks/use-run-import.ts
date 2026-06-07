"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type {
  AmbiguousCompoundModel,
  BatchOptionModel,
  ColumnMappingRequest,
  CompoundBatchOverrideRequest,
  CreateRunImportTemplateRequest,
  HeaderSuggestionModel,
  ImportRunFileRequest,
  ImportRunFileResponse as ImportRunFileResponseModel,
  PlatePreviewModel,
  PreviewRunFileResponse as PreviewRunFileResponseModel,
  ReadoutColumnRequest,
  ReadoutConflictModel,
  RepreviewRunFileRequest,
  ResetRunDataResponse as ResetRunDataResponseModel,
  RunImportTemplateResponse,
  WellConflictModel,
} from "@/shared/lib/api/model";
import { showWarning } from "@/shared/lib/toast";
import {
  DOSE_RESPONSE_KEY,
  PLATE_MAP_KEY,
  READOUT_DATA_KEY,
  RUNS_KEY,
  RUN_IMPORT_TEMPLATES_KEY,
  RUN_KEY,
} from "./query-keys";

/** Compose a non-blocking warning toast body from a fit_warnings array.
 *  Up to 3 lines are shown verbatim; anything beyond is collapsed into a
 *  "+N more" suffix so the toast doesn't grow unbounded on bad runs. */
function buildFitWarningDescription(warnings: string[]): string {
  const head = warnings.slice(0, 3);
  const rest = warnings.length - head.length;
  return rest > 0 ? `${head.join("\n")}\n+${rest} more` : head.join("\n");
}

// ─── Types ─────────────────────────────────────────────────────────────────────
//
// Backend DTOs are aliased from the orval-generated model (the source of truth).
// Never redefine a backend shape here — that silently drifts the moment the
// backend changes.
//
// ``ImportRole`` / ``ImportConfidence`` are the only genuinely client-only types:
// the backend serializes role/confidence as plain strings
// (HeaderSuggestionModelRole = ``string | null``), and these unions narrow that
// loose string for the wizard's role/confidence selects. ``HeaderSuggestion``
// keeps every other field generated-derived (so it can't drift) and only
// narrows those two fields; ``narrowHeaderSuggestions`` does the runtime
// narrowing at the data boundary.

export type ImportRole =
  | "well"
  | "plate_name"
  | "concentration"
  | "batch_ref"
  | "compound_ref"
  | "readout";

export type ImportConfidence = "high" | "medium" | "low";

/** Client-side narrowed view of the generated {@link HeaderSuggestionModel}:
 *  identical shape, but ``role``/``confidence`` are tightened from the backend's
 *  loose ``string`` to the wizard's enums. Use {@link narrowHeaderSuggestions}
 *  to convert the raw model array at the data boundary. */
export type HeaderSuggestion = Omit<HeaderSuggestionModel, "role" | "confidence"> & {
  role: ImportRole | null;
  confidence: ImportConfidence;
};

const IMPORT_ROLES: readonly ImportRole[] = [
  "well",
  "plate_name",
  "concentration",
  "batch_ref",
  "compound_ref",
  "readout",
];

const IMPORT_CONFIDENCES: readonly ImportConfidence[] = ["high", "medium", "low"];

function narrowRole(role: HeaderSuggestionModel["role"]): ImportRole | null {
  return role != null && (IMPORT_ROLES as readonly string[]).includes(role)
    ? (role as ImportRole)
    : null;
}

function narrowConfidence(confidence: string): ImportConfidence {
  return (IMPORT_CONFIDENCES as readonly string[]).includes(confidence)
    ? (confidence as ImportConfidence)
    : "low";
}

/** Tighten the backend's loose role/confidence strings on each suggestion into
 *  the wizard's enums. Unknown roles collapse to ``null`` (ignored column);
 *  unknown confidences collapse to ``"low"`` so they surface for review. */
export function narrowHeaderSuggestions(suggestions: HeaderSuggestionModel[]): HeaderSuggestion[] {
  return suggestions.map((s) => ({
    ...s,
    role: narrowRole(s.role),
    confidence: narrowConfidence(s.confidence),
  }));
}

export type PlatePreview = PlatePreviewModel;
export type WellConflict = WellConflictModel;
export type ReadoutConflict = ReadoutConflictModel;
export type BatchOption = BatchOptionModel;
export type AmbiguousCompound = AmbiguousCompoundModel;
export type PreviewRunFileResponse = PreviewRunFileResponseModel;
export type ReadoutColumnPayload = ReadoutColumnRequest;
export type ColumnMappingPayload = ColumnMappingRequest;
export type CompoundBatchOverride = CompoundBatchOverrideRequest;
export type ImportRunFilePayload = ImportRunFileRequest;
export type ImportRunFileResponse = ImportRunFileResponseModel;
export type RunImportTemplate = RunImportTemplateResponse;

// ─── Hooks ─────────────────────────────────────────────────────────────────────

export function usePreviewRunFile(runId: string) {
  return useMutation({
    mutationFn: async ({ file }: { file: File }) => {
      const formData = new FormData();
      formData.append("file", file);
      return customInstance<PreviewRunFileResponse>({
        url: `${API_V1}/runs/${runId}/preview-file`,
        method: "POST",
        data: formData,
      });
    },
  });
}

export type RepreviewRunFilePayload = RepreviewRunFileRequest;

export function useRepreviewRunFile(runId: string) {
  return useMutation({
    mutationFn: async (payload: RepreviewRunFilePayload) =>
      customInstance<PreviewRunFileResponse>({
        url: `${API_V1}/runs/${runId}/repreview-file`,
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
        url: `${API_V1}/runs/${runId}/import-file`,
        method: "POST",
        data: payload,
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: [...PLATE_MAP_KEY, runId] });
      qc.invalidateQueries({ queryKey: READOUT_DATA_KEY });
      qc.invalidateQueries({ queryKey: DOSE_RESPONSE_KEY });
      qc.invalidateQueries({ queryKey: RUNS_KEY });
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

export type ResetRunDataResponse = ResetRunDataResponseModel;

export function useResetRunData(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () =>
      customInstance<ResetRunDataResponse>({
        url: `${API_V1}/runs/${runId}/reset-data`,
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [...PLATE_MAP_KEY, runId] });
      qc.invalidateQueries({ queryKey: READOUT_DATA_KEY });
      qc.invalidateQueries({ queryKey: DOSE_RESPONSE_KEY });
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      qc.invalidateQueries({ queryKey: [...RUN_KEY, runId] });
    },
  });
}

export function useRunImportTemplates() {
  return useQuery({
    queryKey: RUN_IMPORT_TEMPLATES_KEY,
    queryFn: () =>
      customInstance<RunImportTemplate[]>({
        url: `${API_V1}/run-import-templates`,
        method: "GET",
      }),
  });
}

export function useCreateRunImportTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: CreateRunImportTemplateRequest) =>
      customInstance<RunImportTemplate>({
        url: `${API_V1}/run-import-templates`,
        method: "POST",
        data: input,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["run-import-templates"] });
    },
  });
}
