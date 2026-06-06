import { useCallback, useMemo, useRef, useState } from "react";

import { showError, showSuccess } from "@/shared/lib/toast";
import {
  type SummaryMappingDraft,
  buildMapping,
  suggestionsToDraft,
} from "../lib/summary-import-mapping";
import { useProtocol } from "./use-protocols";
import {
  type SummaryImportResponse,
  type SummaryPreviewResponse,
  type SummaryResolveResponse,
  type SummaryRole,
  useImportSummaryFile,
  usePreviewSummaryFile,
  useResolveSummaryFile,
} from "./use-summary-import";

// ─── Options / result ─────────────────────────────────────────────────────────

export interface UseSummaryImportWizardOptions {
  runId: string;
  protocolId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export interface UseSummaryImportWizardResult {
  // State
  step: 1 | 2 | 3 | 4;
  file: File | null;
  preview: SummaryPreviewResponse | null;
  draft: SummaryMappingDraft;
  resolvePreview: SummaryResolveResponse | null;
  result: SummaryImportResponse | null;

  // Mutations (expose for pending/data inspection in the component)
  previewMutation: ReturnType<typeof usePreviewSummaryFile>;
  resolveMutation: ReturnType<typeof useResolveSummaryFile>;
  importMutation: ReturnType<typeof useImportSummaryFile>;

  // Protocol data — options for the per-readout-column Select
  readoutDefOptions: { id: string; name: string }[];

  // Derived
  canContinueMapping: boolean;
  canImport: boolean;
  isPreviewing: boolean;
  isResolving: boolean;
  isImporting: boolean;

  // Actions
  setStep: (s: 1 | 2 | 3 | 4) => void;
  reset: () => void;
  handleOpenChange: (next: boolean) => void;
  handleFile: (f: File) => void;
  setRole: (header: string, role: SummaryRole) => void;
  setReadoutDef: (header: string, defId: string) => void;
  handleContinueToPreview: () => void;
  handleImport: () => void;
}

// ─── Empty draft ──────────────────────────────────────────────────────────────

function emptyDraft(): SummaryMappingDraft {
  return { roles: {}, readoutDefByHeader: {} };
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useSummaryImportWizard({
  runId,
  protocolId,
  onOpenChange,
}: UseSummaryImportWizardOptions): UseSummaryImportWizardResult {
  // ─── State ──────────────────────────────────────────────────────────────────
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<SummaryPreviewResponse | null>(null);
  const [draft, setDraft] = useState<SummaryMappingDraft>(emptyDraft());
  const [resolvePreview, setResolvePreview] = useState<SummaryResolveResponse | null>(null);
  const [result, setResult] = useState<SummaryImportResponse | null>(null);

  // ─── Mutations / queries ─────────────────────────────────────────────────────
  const previewMutation = usePreviewSummaryFile(runId);
  const resolveMutation = useResolveSummaryFile(runId);
  const importMutation = useImportSummaryFile(runId);
  const { data: protocol } = useProtocol(protocolId);

  const readoutDefOptions = useMemo(
    () =>
      (protocol?.readout_definitions ?? []).map((rd) => ({
        id: rd.id,
        name: rd.name,
      })),
    [protocol?.readout_definitions],
  );

  // TanStack Query returns a fresh mutation object on every render, so keep
  // refs to call .reset() from a stable callback (mirrors use-run-import-wizard).
  const previewMutationRef = useRef(previewMutation);
  previewMutationRef.current = previewMutation;
  const resolveMutationRef = useRef(resolveMutation);
  resolveMutationRef.current = resolveMutation;
  const importMutationRef = useRef(importMutation);
  importMutationRef.current = importMutation;

  // ─── Reset ───────────────────────────────────────────────────────────────────
  const reset = useCallback(() => {
    setStep(1);
    setFile(null);
    setPreview(null);
    setDraft(emptyDraft());
    setResolvePreview(null);
    setResult(null);
    previewMutationRef.current.reset();
    resolveMutationRef.current.reset();
    importMutationRef.current.reset();
  }, []);

  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (!next) reset();
      onOpenChange(next);
    },
    [onOpenChange, reset],
  );

  // ─── Step 1 — file upload ────────────────────────────────────────────────────
  const handleFile = useCallback(
    (f: File) => {
      setFile(f);
      previewMutation.mutate(
        { file: f },
        {
          onSuccess: (data) => {
            setPreview(data);
            setDraft(suggestionsToDraft(data.suggestions));
            setStep(2);
          },
          onError: () => showError("Could not parse file"),
        },
      );
    },
    [previewMutation],
  );

  // ─── Step 2 — role / readout-def mutations ───────────────────────────────────
  const setRole = useCallback((header: string, role: SummaryRole) => {
    setDraft((d) => {
      const nextRoles = { ...d.roles, [header]: role };
      // Changing away from readout drops any prior binding for this header.
      const nextBindings = { ...d.readoutDefByHeader };
      if (role !== "readout" && nextBindings[header]) {
        delete nextBindings[header];
      }
      return { roles: nextRoles, readoutDefByHeader: nextBindings };
    });
  }, []);

  const setReadoutDef = useCallback((header: string, defId: string) => {
    setDraft((d) => ({
      ...d,
      readoutDefByHeader: { ...d.readoutDefByHeader, [header]: defId },
    }));
  }, []);

  const canContinueMapping = useMemo(() => buildMapping(draft) !== null, [draft]);

  // ─── Step 2 → 3 — dry-run resolve with the chemist's confirmed mapping ────────
  const handleContinueToPreview = useCallback(() => {
    if (!file) return;
    const mapping = buildMapping(draft);
    if (!mapping) {
      showError("Mapping incomplete — assign a compound/batch column and bind every readout");
      return;
    }
    resolveMutation.mutate(
      { file, mapping },
      {
        onSuccess: (data) => {
          setResolvePreview(data);
          setStep(3);
        },
        onError: () => showError("Could not resolve the import"),
      },
    );
  }, [file, draft, resolveMutation]);

  // ─── Step 3 → 4 — commit ─────────────────────────────────────────────────────
  const canImport = useMemo(
    () =>
      resolvePreview != null &&
      resolvePreview.values_to_insert + resolvePreview.values_to_update > 0,
    [resolvePreview],
  );

  const handleImport = useCallback(() => {
    if (!file) return;
    const mapping = buildMapping(draft);
    if (!mapping) {
      showError("Mapping incomplete — assign a compound/batch column and bind every readout");
      return;
    }
    importMutation.mutate(
      { file, mapping },
      {
        onSuccess: (data) => {
          setResult(data);
          showSuccess(`Imported ${data.values_inserted + data.values_updated} values`);
          setStep(4);
        },
        onError: () => showError("Import failed"),
      },
    );
  }, [file, draft, importMutation]);

  // ─── Return ──────────────────────────────────────────────────────────────────
  return {
    step,
    file,
    preview,
    draft,
    resolvePreview,
    result,
    previewMutation,
    resolveMutation,
    importMutation,
    readoutDefOptions,
    canContinueMapping,
    canImport,
    isPreviewing: previewMutation.isPending,
    isResolving: resolveMutation.isPending,
    isImporting: importMutation.isPending,
    setStep,
    reset,
    handleOpenChange,
    handleFile,
    setRole,
    setReadoutDef,
    handleContinueToPreview,
    handleImport,
  };
}
