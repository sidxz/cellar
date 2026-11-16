"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { API_V1, ApiError, customInstance } from "@/shared/lib/api/custom-instance";
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
import { showInfo, showWarning } from "@/shared/lib/toast";
import {
  DOSE_RESPONSE_KEY,
  MEASURED_CURVES_KEY,
  MELTING_ANALYSIS_KEY,
  PLATE_MAP_KEY,
  READOUT_DATA_KEY,
  RUNS_KEY,
  RUN_IMPORT_TEMPLATES_KEY,
  RUN_KEY,
} from "./query-keys";

/** Warn of a refit's failed fits, each naming its compound: up to 3 lines verbatim,
 *  anything beyond collapsed into a "+N more" suffix so the toast doesn't grow unbounded
 *  on bad runs. Compounds tested at too few doses are not failures: they ride in the
 *  refit's notes. */
export function showFitFailures(warnings: string[] | undefined, prefix = ""): void {
  if (!warnings?.length) return;
  const head = warnings.slice(0, 3);
  const rest = warnings.length - head.length;
  const n = warnings.length;
  showWarning(`${prefix}${n} curve fit${n === 1 ? "" : "s"} failed`, {
    description: rest > 0 ? `${head.join("\n")}\n+${rest} more` : head.join("\n"),
  });
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
  | "readout"
  | "well_role";

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
  "well_role",
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

function uploadPreview(runId: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return customInstance<PreviewRunFileResponse>({
    url: `${API_V1}/runs/${runId}/preview-file`,
    method: "POST",
    data: formData,
  });
}

export function usePreviewRunFile(runId: string) {
  return useMutation({
    mutationFn: async ({ file }: { file: File }) => uploadPreview(runId, file),
  });
}

/** The server keeps a preview 30 minutes from its last use and loses it on a restart. */
export class PreviewExpiredError extends Error {
  constructor() {
    super("The preview expired — upload the file again");
    this.name = "PreviewExpiredError";
  }
}

function isMissingPreview(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 404) return false;
  const message = (error.body as { message?: unknown } | null)?.message;
  return typeof message === "string" && message.startsWith("Preview ");
}

/** Run ``call`` against the preview; when the server no longer holds it, upload the
 *  file again and retry with the fresh preview — the chemist's mapping and picks
 *  survive. Only when that fails too is the preview reported expired. */
async function withLivePreview<T>(
  runId: string,
  file: File | null,
  previewId: string,
  call: (previewId: string) => Promise<T>,
): Promise<T> {
  try {
    return await call(previewId);
  } catch (error) {
    if (!isMissingPreview(error)) throw error;
  }
  const fresh = file ? await uploadPreview(runId, file).catch(() => null) : null;
  if (!fresh) throw new PreviewExpiredError();
  return call(fresh.preview_id).catch((error: unknown) => {
    throw isMissingPreview(error) ? new PreviewExpiredError() : error;
  });
}

/** The file the wizard still holds, for re-uploading an expired preview. */
type WithFile<T> = T & { file: File | null };

export type RepreviewRunFilePayload = RepreviewRunFileRequest;

export function useRepreviewRunFile(runId: string) {
  return useMutation({
    mutationFn: async ({ file, ...payload }: WithFile<RepreviewRunFilePayload>) =>
      withLivePreview(runId, file, payload.preview_id, (preview_id) =>
        customInstance<PreviewRunFileResponse>({
          url: `${API_V1}/runs/${runId}/repreview-file`,
          method: "POST",
          data: { ...payload, preview_id },
        }),
      ),
  });
}

export function useImportRunFile(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, ...payload }: WithFile<ImportRunFilePayload>) =>
      withLivePreview(runId, file, payload.preview_id, (preview_id) =>
        customInstance<ImportRunFileResponse>({
          url: `${API_V1}/runs/${runId}/import-file`,
          method: "POST",
          data: { ...payload, preview_id },
        }),
      ),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: [...PLATE_MAP_KEY, runId] });
      qc.invalidateQueries({ queryKey: READOUT_DATA_KEY });
      qc.invalidateQueries({ queryKey: DOSE_RESPONSE_KEY });
      qc.invalidateQueries({ queryKey: RUNS_KEY });
      qc.invalidateQueries({ queryKey: ["attachments", "run", runId] });
      if (data.fit_notes?.length) showInfo(data.fit_notes.join("\n"));
      showFitFailures(data.fit_warnings, "Run imported. ");
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
      qc.invalidateQueries({ queryKey: MEASURED_CURVES_KEY });
      qc.invalidateQueries({ queryKey: [...MELTING_ANALYSIS_KEY, runId] });
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
