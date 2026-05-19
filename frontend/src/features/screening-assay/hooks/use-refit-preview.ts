"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type {
  RefitPreviewRequest,
  RefitPreviewResponse,
} from "@/shared/lib/api/model";
import { refitDoseResponseCurvePreviewApiV1DoseResponseCurvesCurveIdRefitPreviewPost } from "@/shared/lib/api/readout-data/readout-data";

export interface UseRefitPreviewOptions {
  debounceMs?: number;
  /** Injectable for tests. Default delegates to the orval-generated call. */
  previewFn?: (
    curveId: string,
    body: RefitPreviewRequest,
    signal?: AbortSignal,
  ) => Promise<RefitPreviewResponse>;
}

export interface UseRefitPreviewApi {
  data: RefitPreviewResponse | null;
  isPreviewing: boolean;
  error: Error | null;
  requestPreview: (curveId: string, excludedIndices: number[]) => void;
  reset: () => void;
}

/**
 * Debounced compute-only preview hook for dose-response refits.
 *
 * Batches rapid point-toggle requests into a single ``/refit-preview`` network
 * call (default 300ms debounce). Cancels any in-flight request when a newer
 * one arrives so the chart always reflects the latest draft.
 *
 * On error: preserves the previous ``data`` so a transient failure does not
 * blank the chart — the chemist keeps seeing the last good preview.
 *
 * On abort: silent — aborts are expected when the user is toggling rapidly.
 */
export function useRefitPreview(
  options: UseRefitPreviewOptions = {},
): UseRefitPreviewApi {
  const debounceMs = options.debounceMs ?? 300;
  const previewFn = options.previewFn ?? defaultPreviewFn;
  // Pin the latest previewFn in a ref so requestPreview doesn't change identity
  // every render. This matters because the chart calls requestPreview inside an
  // effect keyed on the draft — re-creating it would loop.
  const previewFnRef = useRef(previewFn);
  useEffect(() => {
    previewFnRef.current = previewFn;
  }, [previewFn]);

  const [data, setData] = useState<RefitPreviewResponse | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const requestPreview = useCallback(
    (curveId: string, excludedIndices: number[]) => {
      // Cancel any pending debounce (collapse rapid toggles into one call).
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
      // Cancel any in-flight call — a newer draft just arrived.
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
      setIsPreviewing(true);
      setError(null);

      debounceRef.current = setTimeout(() => {
        debounceRef.current = null;
        const ac = new AbortController();
        abortRef.current = ac;
        previewFnRef
          .current(curveId, { excluded_indices: excludedIndices }, ac.signal)
          .then((response) => {
            if (ac.signal.aborted) return;
            setData(response);
            setIsPreviewing(false);
          })
          .catch((err: unknown) => {
            // Aborts are expected — stay silent and keep the chart frozen
            // on the last good preview.
            if (ac.signal.aborted) return;
            if (err instanceof Error && err.name === "AbortError") return;
            setError(err instanceof Error ? err : new Error(String(err)));
            setIsPreviewing(false);
          });
      }, debounceMs);
    },
    [debounceMs],
  );

  const reset = useCallback(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setData(null);
    setError(null);
    setIsPreviewing(false);
  }, []);

  // Cleanup on unmount: clear timer + abort any in-flight call.
  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (abortRef.current) abortRef.current.abort();
    },
    [],
  );

  return { data, isPreviewing, error, requestPreview, reset };
}

async function defaultPreviewFn(
  curveId: string,
  body: RefitPreviewRequest,
  signal?: AbortSignal,
): Promise<RefitPreviewResponse> {
  return refitDoseResponseCurvePreviewApiV1DoseResponseCurvesCurveIdRefitPreviewPost(
    curveId,
    body,
    signal,
  );
}
