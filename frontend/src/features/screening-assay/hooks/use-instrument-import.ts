"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { STALE_TIME } from "@/shared/lib/query-defaults";
import type {
  InstrumentFileFormats,
  InstrumentImportResult,
  InstrumentPreview,
  WellType,
} from "../types";
import {
  DOSE_RESPONSE_KEY,
  INSTRUMENT_FILE_FORMATS_KEY,
  MEASURED_CURVES_KEY,
  MELTING_ANALYSIS_KEY,
  PLATE_MAP_KEY,
  READOUT_DATA_KEY,
  RUNS_KEY,
  RUN_KEY,
} from "./query-keys";

// ─── FE-local request payload (NOT a backend DTO) ────────────────────────────────
// Sent as the JSON-stringified `labelling` FormData field, so orval emits no model
// for it. Mirrors the backend's InstrumentLabellingRequest.
export interface InstrumentLabelling {
  positions: {
    row: number;
    column: number;
    used: boolean;
    label: string;
    note: string;
    well_type: WellType;
    batch_id: string | null;
    dose: number | null;
  }[];
  series: { channel: string; kind: string; ordinal: number; readout_definition_id: string }[];
}

/** The instrument files the import reads, with which export to make; fixed for the session.
 *  GET /api/v1/instrument-file-formats. */
export function useInstrumentFileFormats() {
  return useQuery({
    queryKey: INSTRUMENT_FILE_FORMATS_KEY,
    queryFn: () =>
      customInstance<InstrumentFileFormats>({
        url: `${API_V1}/instrument-file-formats`,
        method: "GET",
      }),
    staleTime: STALE_TIME.STATIC,
  });
}

/** Read an instrument file and propose a labelling. Writes nothing.
 *  POST /api/v1/runs/{runId}/preview-instrument-file (multipart: file). */
export function usePreviewInstrumentFile(runId: string) {
  return useMutation({
    mutationFn: async ({ file }: { file: File }) => {
      const formData = new FormData();
      formData.append("file", file);
      return customInstance<InstrumentPreview>({
        url: `${API_V1}/runs/${runId}/preview-instrument-file`,
        method: "POST",
        data: formData,
      });
    },
  });
}

/** Store the file's curves and mapped reported values on the run.
 *  POST /api/v1/runs/{runId}/import-instrument-file
 *  (multipart: file + labelling = JSON.stringify(InstrumentLabelling)). */
export function useImportInstrumentFile(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, labelling }: { file: File; labelling: InstrumentLabelling }) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("labelling", JSON.stringify(labelling));
      return customInstance<InstrumentImportResult>({
        url: `${API_V1}/runs/${runId}/import-instrument-file`,
        method: "POST",
        data: formData,
      });
    },
    onSuccess: () => {
      for (const queryKey of [
        READOUT_DATA_KEY,
        DOSE_RESPONSE_KEY,
        PLATE_MAP_KEY,
        MEASURED_CURVES_KEY,
        [...MELTING_ANALYSIS_KEY, runId],
        RUNS_KEY,
        [...RUN_KEY, runId],
      ]) {
        qc.invalidateQueries({ queryKey });
      }
    },
  });
}
