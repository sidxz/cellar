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
  type SummaryRole,
  useImportSummaryFile,
  usePreviewSummaryFile,
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
  step: 1 | 2 | 3;
  file: File | null;
  preview: SummaryPreviewResponse | null;
  draft: SummaryMappingDraft;
  result: SummaryImportResponse | null;
  isDragging: boolean;
  fileInputRef: React.RefObject<HTMLInputElement | null>;

  // Mutations (expose for pending/data inspection in the component)
  previewMutation: ReturnType<typeof usePreviewSummaryFile>;
  importMutation: ReturnType<typeof useImportSummaryFile>;

  // Protocol data — options for the per-readout-column Select
  readoutDefOptions: { id: string; name: string }[];

  // Derived
  canContinueMapping: boolean;
  isPreviewing: boolean;
  isImporting: boolean;

  // Actions
  setStep: (s: 1 | 2 | 3) => void;
  setIsDragging: (v: boolean) => void;
  reset: () => void;
  handleOpenChange: (next: boolean) => void;
  handleFile: (f: File) => void;
  handleDrop: (e: React.DragEvent) => void;
  setRole: (header: string, role: SummaryRole) => void;
  setReadoutDef: (header: string, defId: string) => void;
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
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<SummaryPreviewResponse | null>(null);
  const [draft, setDraft] = useState<SummaryMappingDraft>(emptyDraft());
  const [result, setResult] = useState<SummaryImportResponse | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  // ─── Mutations / queries ─────────────────────────────────────────────────────
  const previewMutation = usePreviewSummaryFile(runId);
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
  const importMutationRef = useRef(importMutation);
  importMutationRef.current = importMutation;

  // ─── Reset ───────────────────────────────────────────────────────────────────
  const reset = useCallback(() => {
    setStep(1);
    setFile(null);
    setPreview(null);
    setDraft(emptyDraft());
    setResult(null);
    previewMutationRef.current.reset();
    importMutationRef.current.reset();
    if (fileInputRef.current) fileInputRef.current.value = "";
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

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const f = e.dataTransfer.files[0];
      if (f) handleFile(f);
    },
    [handleFile],
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

  // ─── Step 3 — submit ─────────────────────────────────────────────────────────
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
          setStep(3);
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
    result,
    isDragging,
    fileInputRef,
    previewMutation,
    importMutation,
    readoutDefOptions,
    canContinueMapping,
    isPreviewing: previewMutation.isPending,
    isImporting: importMutation.isPending,
    setStep,
    setIsDragging,
    reset,
    handleOpenChange,
    handleFile,
    handleDrop,
    setRole,
    setReadoutDef,
    handleImport,
  };
}
