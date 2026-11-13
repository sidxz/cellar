import { useCallback, useMemo, useRef, useState } from "react";

import {
  type LabellingDraft,
  type PositionDraft,
  buildLabelling,
  draftFromPreview,
  setRoleForPositions,
} from "../lib/instrument-labelling";
import type { InstrumentImportResult, InstrumentPreview, WellType } from "../types";
import { useImportInstrumentFile, usePreviewInstrumentFile } from "./use-instrument-import";

export interface UseInstrumentImportWizardOptions {
  runId: string;
  onOpenChange: (open: boolean) => void;
}

export interface UseInstrumentImportWizardResult {
  step: 1 | 2 | 3 | 4;
  file: File | null;
  preview: InstrumentPreview | null;
  draft: LabellingDraft;
  result: InstrumentImportResult | null;
  /** The API's reason the last preview or import was refused, worded as it sent it. */
  error: string | null;
  isPreviewing: boolean;
  isImporting: boolean;
  /** A preview exists and every used position holds valid values. */
  canImport: boolean;
  handleFile: (f: File) => void;
  updatePosition: (key: string, patch: Partial<PositionDraft>) => void;
  setRole: (keys: ReadonlySet<string>, wellType: WellType) => void;
  setSeriesReadout: (key: string, readoutId: string | null) => void;
  setStep: (s: 1 | 2 | 3 | 4) => void;
  handleImport: () => void;
  handleOpenChange: (next: boolean) => void;
}

const EMPTY_DRAFT: LabellingDraft = { positions: [], readoutBySeries: {} };

// ApiError.message reads "API error: 422 — <detail>"; the detail alone is the API's wording.
export const apiReason = (e: unknown) =>
  (e instanceof Error ? e.message : String(e)).replace(/^API error: \d+ — /, "");

export function useInstrumentImportWizard({
  runId,
  onOpenChange,
}: UseInstrumentImportWizardOptions): UseInstrumentImportWizardResult {
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<InstrumentPreview | null>(null);
  const [draft, setDraft] = useState<LabellingDraft>(EMPTY_DRAFT);
  const [result, setResult] = useState<InstrumentImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const previewMutation = usePreviewInstrumentFile(runId);
  const importMutation = useImportInstrumentFile(runId);
  // Mutation objects change every render; reset them from a stable callback.
  const mutationsRef = useRef({ previewMutation, importMutation });
  mutationsRef.current = { previewMutation, importMutation };

  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (!next) {
        setStep(1);
        setFile(null);
        setPreview(null);
        setDraft(EMPTY_DRAFT);
        setResult(null);
        setError(null);
        mutationsRef.current.previewMutation.reset();
        mutationsRef.current.importMutation.reset();
      }
      onOpenChange(next);
    },
    [onOpenChange],
  );

  const handleFile = useCallback(
    (f: File) => {
      setFile(f);
      setPreview(null);
      setDraft(EMPTY_DRAFT);
      setError(null);
      previewMutation.mutate(
        { file: f },
        {
          onSuccess: (data) => {
            setPreview(data);
            setDraft(draftFromPreview(data));
          },
          onError: (e) => setError(apiReason(e)),
        },
      );
    },
    [previewMutation],
  );

  const updatePosition = useCallback((key: string, patch: Partial<PositionDraft>) => {
    setDraft((d) => ({
      ...d,
      positions: d.positions.map((p) => (p.key === key ? { ...p, ...patch } : p)),
    }));
  }, []);

  const setRole = useCallback((keys: ReadonlySet<string>, wellType: WellType) => {
    setDraft((d) => setRoleForPositions(d, keys, wellType));
  }, []);

  const setSeriesReadout = useCallback((key: string, readoutId: string | null) => {
    setDraft((d) => ({ ...d, readoutBySeries: { ...d.readoutBySeries, [key]: readoutId } }));
  }, []);

  const labelling = useMemo(
    () => (preview ? buildLabelling(draft, preview) : null),
    [draft, preview],
  );

  const handleImport = useCallback(() => {
    if (!file || !labelling) return;
    setError(null);
    importMutation.mutate(
      { file, labelling },
      {
        onSuccess: setResult,
        onError: (e) => setError(apiReason(e)),
      },
    );
  }, [file, labelling, importMutation]);

  return {
    step,
    file,
    preview,
    draft,
    result,
    error,
    isPreviewing: previewMutation.isPending,
    isImporting: importMutation.isPending,
    canImport: labelling !== null,
    handleFile,
    updatePosition,
    setRole,
    setSeriesReadout,
    setStep,
    handleImport,
    handleOpenChange,
  };
}
