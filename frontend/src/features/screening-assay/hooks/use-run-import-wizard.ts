import { useCallback, useMemo, useRef, useState } from "react";

import { useProtocol } from "./use-protocols";
import {
  useCreateRunImportTemplate,
  useImportRunFile,
  usePreviewRunFile,
  useRepreviewRunFile,
  useRunImportTemplates,
  type ColumnMappingPayload,
  type ImportRole,
  type PreviewRunFileResponse,
  type ReadoutColumnPayload,
  type RunImportTemplate,
} from "./use-run-import";
import {
  applyTemplateToDraft,
  emptyDraft,
  pickBestTemplate,
  suggestionToInitialDraft,
  type MappingDraft,
} from "../lib/run-import-mapping";
import { showError, showSuccess } from "@/shared/lib/toast";

// ─── Hook ─────────────────────────────────────────────────────────────────────

export interface UseRunImportWizardOptions {
  runId: string;
  protocolId: string;
  onClose: () => void;
}

export interface UseRunImportWizardResult {
  // State
  step: 1 | 2 | 3 | 4;
  file: File | null;
  preview: PreviewRunFileResponse | null;
  draft: MappingDraft;
  setDraft: React.Dispatch<React.SetStateAction<MappingDraft>>;
  appliedTemplate: RunImportTemplate | null;
  saveAsTemplate: boolean;
  templateName: string;
  compoundPicks: Record<string, string>;
  isDragging: boolean;
  fileInputRef: React.RefObject<HTMLInputElement | null>;

  // Mutations (expose for pending/data inspection in the component)
  previewMutation: ReturnType<typeof usePreviewRunFile>;
  repreviewMutation: ReturnType<typeof useRepreviewRunFile>;
  importMutation: ReturnType<typeof useImportRunFile>;
  createTemplate: ReturnType<typeof useCreateRunImportTemplate>;

  // Protocol data
  readoutDefs: { id: string; name: string }[];
  protocol: ReturnType<typeof useProtocol>["data"];

  // Derived
  wellHeader: string | null;
  lowConfidenceHeaders: string[];
  readoutHeaders: string[];
  canContinueStep2: boolean;

  // Actions
  setStep: (s: 1 | 2 | 3 | 4) => void;
  setIsDragging: (v: boolean) => void;
  setAppliedTemplate: (t: RunImportTemplate | null) => void;
  setSaveAsTemplate: (v: boolean) => void;
  setTemplateName: (v: string) => void;
  setCompoundPicks: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  reset: () => void;
  handleOpenChange: (next: boolean) => void;
  handleFile: (f: File) => void;
  handleDrop: (e: React.DragEvent) => void;
  handleSetRole: (header: string, role: ImportRole | "ignore") => void;
  handleSetReadoutDef: (header: string, defId: string) => void;
  handleContinueFromMapping: () => void;
  buildMapping: () => ColumnMappingPayload | null;
  handleSubmit: () => void;
}

export function useRunImportWizard({
  runId,
  protocolId,
  onClose,
}: UseRunImportWizardOptions): UseRunImportWizardResult {
  // ─── State ──────────────────────────────────────────────────────────────────
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewRunFileResponse | null>(null);
  const [draft, setDraft] = useState<MappingDraft>(emptyDraft());
  const [appliedTemplate, setAppliedTemplate] = useState<RunImportTemplate | null>(null);
  const [saveAsTemplate, setSaveAsTemplate] = useState(false);
  const [templateName, setTemplateName] = useState("");
  // Per-molecule batch picks from the disambiguation panel. Cleared when
  // the wizard resets. ``molecule_id -> batch_id``.
  const [compoundPicks, setCompoundPicks] = useState<Record<string, string>>({});

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  // ─── Mutations / queries ─────────────────────────────────────────────────────
  const previewMutation = usePreviewRunFile(runId);
  const repreviewMutation = useRepreviewRunFile(runId);
  const importMutation = useImportRunFile(runId);
  const createTemplate = useCreateRunImportTemplate();
  const { data: templates = [] } = useRunImportTemplates();
  const { data: protocol } = useProtocol(protocolId);

  const readoutDefs = protocol?.readout_definitions ?? [];

  // TanStack Query returns a fresh mutation object on every render, so
  // depending on the mutation in a useCallback would re-create reset every
  // render and (combined with the close-effect in the component) trip an
  // infinite loop. Stash them in refs so reset stays stable.
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
    setAppliedTemplate(null);
    setSaveAsTemplate(false);
    setTemplateName("");
    setCompoundPicks({});
    previewMutationRef.current.reset();
    importMutationRef.current.reset();
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (!next) reset();
      onClose();
    },
    [onClose, reset],
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
            setDraft(suggestionToInitialDraft(data.suggestions));
            setCompoundPicks({});
            // Auto-suggest a matching template if any header set lines up.
            const match = pickBestTemplate(templates, data.headers);
            if (match) {
              setAppliedTemplate(match);
              setDraft((d) => applyTemplateToDraft(d, match, data.headers));
            }
            setStep(2);
          },
          onError: () => showError("Could not parse file"),
        },
      );
    },
    [previewMutation, templates],
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

  // ─── Step 2 — mapping derived values ─────────────────────────────────────────
  const wellHeader = useMemo(() => {
    return Object.entries(draft.roles).find(([, r]) => r === "well")?.[0] ?? null;
  }, [draft.roles]);

  const lowConfidenceHeaders = useMemo(() => {
    if (!preview) return [] as string[];
    return preview.suggestions
      .filter((s) => s.confidence === "low" && draft.roles[s.header] !== null)
      .map((s) => s.header);
  }, [preview, draft.roles]);

  const readoutHeaders = useMemo(
    () =>
      Object.entries(draft.roles)
        .filter(([, r]) => r === "readout")
        .map(([h]) => h),
    [draft.roles],
  );

  const allReadoutsBound = readoutHeaders.every((h) => !!draft.readoutDefByHeader[h]);

  const canContinueStep2 =
    !!wellHeader &&
    readoutHeaders.length > 0 &&
    allReadoutsBound &&
    (lowConfidenceHeaders.length === 0 || draft.acknowledgedLowConfidence);

  // ─── Step 2 — role/readout-def mutations ────────────────────────────────────
  const handleSetRole = useCallback((header: string, role: ImportRole | "ignore") => {
    setDraft((d) => {
      const nextRoles = { ...d.roles };
      // well / plate_name / concentration / batch_ref / compound_ref are
      // unique — only one column can carry each. Reassigning the same role to
      // a new header clears the prior holder.
      const unique: ImportRole[] = [
        "well",
        "plate_name",
        "concentration",
        "batch_ref",
        "compound_ref",
      ];
      const r: ImportRole | null = role === "ignore" ? null : role;
      if (r && unique.includes(r)) {
        for (const [h, existing] of Object.entries(nextRoles)) {
          if (existing === r && h !== header) {
            nextRoles[h] = null;
          }
        }
      }
      nextRoles[header] = r;
      // If we changed away from readout, drop the binding.
      const nextBindings = { ...d.readoutDefByHeader };
      if (r !== "readout" && nextBindings[header]) {
        delete nextBindings[header];
      }
      return { ...d, roles: nextRoles, readoutDefByHeader: nextBindings };
    });
  }, []);

  const handleSetReadoutDef = useCallback((header: string, defId: string) => {
    setDraft((d) => ({
      ...d,
      readoutDefByHeader: { ...d.readoutDefByHeader, [header]: defId },
    }));
  }, []);

  // ─── Step 2 → 3 — re-resolve with the chemist's confirmed mapping ────────────
  const buildMapping = useCallback((): ColumnMappingPayload | null => {
    if (!wellHeader) return null;
    const find = (role: ImportRole): string | null =>
      Object.entries(draft.roles).find(([, r]) => r === role)?.[0] ?? null;

    const readout_columns: ReadoutColumnPayload[] = readoutHeaders.map((h) => ({
      header: h,
      readout_definition_id: draft.readoutDefByHeader[h]!,
    }));

    return {
      well: wellHeader,
      plate_name: find("plate_name"),
      concentration: find("concentration"),
      batch_ref: find("batch_ref"),
      compound_ref: find("compound_ref"),
      readout_columns,
    };
  }, [wellHeader, draft.roles, draft.readoutDefByHeader, readoutHeaders]);

  const handleContinueFromMapping = useCallback(() => {
    if (!preview) return;
    const mapping = buildMapping();
    if (!mapping) {
      showError("Mapping incomplete — pick a Well column.");
      return;
    }
    repreviewMutation.mutate(
      {
        preview_id: preview.preview_id,
        mapping,
      },
      {
        onSuccess: (data) => {
          setPreview(data);
          // The set of ambiguous molecules can change when the mapping changes
          // (different column → different compound refs). Drop stale picks so
          // the panel forces a fresh decision.
          setCompoundPicks({});
          setStep(3);
        },
        onError: () => showError("Could not re-resolve with the new mapping"),
      },
    );
  }, [preview, buildMapping, repreviewMutation]);

  // ─── Step 4 — submit ─────────────────────────────────────────────────────────
  const handleSubmit = useCallback(() => {
    if (!preview) return;
    const mapping = buildMapping();
    if (!mapping) {
      showError("Mapping incomplete — pick a Well column.");
      return;
    }
    importMutation.mutate(
      {
        preview_id: preview.preview_id,
        mapping,
        compound_batch_overrides: Object.entries(compoundPicks).map(
          ([molecule_id, batch_id]) => ({ molecule_id, batch_id }),
        ),
      },
      {
        onSuccess: (data) => {
          showSuccess(
            `Imported ${data.wells_created} wells / ${data.readouts_created} readouts`,
          );
          if (saveAsTemplate && templateName.trim()) {
            const column_mapping: Record<string, unknown> = {
              well: mapping.well,
              plate_name: mapping.plate_name,
              concentration: mapping.concentration,
              batch_ref: mapping.batch_ref,
              compound_ref: mapping.compound_ref,
              readout_headers: mapping.readout_columns.map((rc) => rc.header),
            };
            createTemplate.mutate({
              name: templateName.trim(),
              column_mapping,
            });
          }
          setStep(4);
        },
        onError: () => showError("Import failed"),
      },
    );
  }, [preview, buildMapping, compoundPicks, importMutation, saveAsTemplate, templateName, createTemplate]);

  // ─── Return ──────────────────────────────────────────────────────────────────
  return {
    step,
    file,
    preview,
    draft,
    setDraft,
    appliedTemplate,
    saveAsTemplate,
    templateName,
    compoundPicks,
    isDragging,
    fileInputRef,
    previewMutation,
    repreviewMutation,
    importMutation,
    createTemplate,
    readoutDefs,
    protocol,
    wellHeader,
    lowConfidenceHeaders,
    readoutHeaders,
    canContinueStep2,
    setStep,
    setIsDragging,
    setAppliedTemplate,
    setSaveAsTemplate,
    setTemplateName,
    setCompoundPicks,
    reset,
    handleOpenChange,
    handleFile,
    handleDrop,
    handleSetRole,
    handleSetReadoutDef,
    handleContinueFromMapping,
    buildMapping,
    handleSubmit,
  };
}
