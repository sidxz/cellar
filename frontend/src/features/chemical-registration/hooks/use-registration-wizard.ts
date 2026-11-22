"use client";

import type { ColumnMappingBody } from "@/shared/lib/api/model";
import { create } from "zustand";
import type { FileColumns } from "../lib/read-file-columns";
import type { RegistrationResponse } from "../types/index";
import type {
  BulkInput,
  BulkProgress,
  ConfirmMergesResponse,
  MergeCandidateRef,
  PreviewBulkRegistrationResponse,
  SingleInput,
  WizardMode,
} from "../types/registration-wizard";

// ─── Batch sub-state ────────────────────────────────────────────────────────

export interface WizardBatchInput {
  source: string;
  amountValue: number | null;
  amountUnit: string;
  purity: number | null;
  saltEntryId: string | null;
  saltStoichiometry: number;
  appearance: string | null;
}

// ─── Default values ─────────────────────────────────────────────────────────

const DEFAULT_SINGLE_INPUT: SingleInput = {
  name: "",
  smiles: null,
  moleculeType: "small_molecule",
  discloser: { userId: null, orgId: null },
  externalIds: [],
  customFields: {},
  disclosureMode: false,
  moleculeId: null,
  scientistName: "",
  disclosingOrgId: null,
  notes: "",
  projectIds: [],
};

const DEFAULT_BULK_INPUT: BulkInput = {
  file: null,
  fileFormat: "csv",
  parsedRows: [],
  discloser: { userId: null, orgId: null },
  createBatchOnDuplicate: false,
  projectIds: [],
};

// ─── Store interface ─────────────────────────────────────────────────────────

interface RegistrationWizardState {
  // Navigation
  mode: WizardMode | null;
  currentStep: number;

  // Input data
  singleInput: SingleInput;
  bulkInput: BulkInput;
  batchInput: WizardBatchInput | null;

  // Bulk "Match columns": the file's columns and where each one goes
  bulkColumns: FileColumns | null;
  bulkMapping: ColumnMappingBody | null;

  // Bulk preview (parse-only result before processing starts)
  bulkPreview: PreviewBulkRegistrationResponse | null;

  // Job tracking
  workflowId: string | null;
  progress: BulkProgress | null;

  // Results
  singleResult: RegistrationResponse | null;
  mergeCandidates: MergeCandidateRef[];
  mergeDecisions: Record<string, "confirm" | "reject">;
  mergeOutcomes: ConfirmMergesResponse | null;

  // ─── Actions ──────────────────────────────────────────────────────────────

  setMode: (mode: WizardMode) => void;
  setCurrentStep: (step: number) => void;
  nextStep: () => void;
  prevStep: () => void;

  updateSingleInput: (patch: Partial<SingleInput>) => void;
  updateBulkInput: (patch: Partial<BulkInput>) => void;

  setBulkColumns: (columns: FileColumns | null) => void;
  /** A changed mapping invalidates the preview. */
  setBulkMapping: (mapping: ColumnMappingBody | null) => void;
  setBulkPreview: (preview: PreviewBulkRegistrationResponse | null) => void;
  setWorkflowId: (id: string | null) => void;
  setProgress: (progress: BulkProgress | null) => void;
  setSingleResult: (result: RegistrationResponse | null) => void;

  /** Replaces the merge candidate list and initialises all decisions to "confirm". */
  setMergeCandidates: (candidates: MergeCandidateRef[]) => void;
  /** Set the decision for a single disclosure. */
  setMergeDecision: (disclosureId: string, decision: "confirm" | "reject") => void;
  setMergeOutcomes: (outcome: ConfirmMergesResponse) => void;
  /** Mark every candidate as confirmed. */
  confirmAllMerges: () => void;
  /** Mark every candidate as rejected. */
  rejectAllMerges: () => void;

  setBatchInput: (batch: WizardBatchInput | null) => void;

  reset: () => void;
}

// ─── Store implementation ────────────────────────────────────────────────────

export const useRegistrationWizard = create<RegistrationWizardState>()((set, _get) => ({
  // Initial state
  mode: null,
  currentStep: 0,
  singleInput: DEFAULT_SINGLE_INPUT,
  bulkInput: DEFAULT_BULK_INPUT,
  batchInput: null,
  bulkColumns: null,
  bulkMapping: null,
  bulkPreview: null,
  workflowId: null,
  progress: null,
  singleResult: null,
  mergeCandidates: [],
  mergeDecisions: {},
  mergeOutcomes: null,

  // Navigation
  setMode: (mode) => set({ mode, currentStep: 0 }),
  setCurrentStep: (step) => set({ currentStep: step }),
  nextStep: () => set((s) => ({ currentStep: s.currentStep + 1 })),
  prevStep: () => set((s) => ({ currentStep: Math.max(0, s.currentStep - 1) })),

  // Input updates
  updateSingleInput: (patch) => set((s) => ({ singleInput: { ...s.singleInput, ...patch } })),
  updateBulkInput: (patch) =>
    set((s) => {
      const bulkInput = { ...s.bulkInput, ...patch };
      // A different file has different columns: start its mapping and preview over.
      return "file" in patch && patch.file !== s.bulkInput.file
        ? { bulkInput, bulkColumns: null, bulkMapping: null, bulkPreview: null }
        : { bulkInput };
    }),

  // Bulk mapping + preview
  setBulkColumns: (bulkColumns) => set({ bulkColumns }),
  setBulkMapping: (bulkMapping) => set({ bulkMapping, bulkPreview: null }),
  setBulkPreview: (bulkPreview) => set({ bulkPreview }),

  // Job tracking
  setWorkflowId: (workflowId) => set({ workflowId }),
  setProgress: (progress) => set({ progress }),
  setSingleResult: (singleResult) => set({ singleResult }),

  // Merge decisions
  setMergeCandidates: (candidates) => {
    const decisions: Record<string, "confirm" | "reject"> = {};
    for (const c of candidates) {
      decisions[c.disclosure_id] = "confirm";
    }
    set({ mergeCandidates: candidates, mergeDecisions: decisions });
  },
  setMergeDecision: (disclosureId, decision) =>
    set((s) => ({
      mergeDecisions: { ...s.mergeDecisions, [disclosureId]: decision },
    })),
  setMergeOutcomes: (outcome) =>
    set((state) => {
      const previous = state.mergeOutcomes;
      const results = new Map(
        (previous?.results ?? []).map((result) => [result.disclosure_id, result]),
      );
      for (const result of outcome.results) results.set(result.disclosure_id, result);
      return {
        mergeOutcomes: {
          results: [...results.values()],
          confirmed_count: [...results.values()].filter(
            (result) => result.success && result.action === "confirm",
          ).length,
          rejected_count: [...results.values()].filter(
            (result) => result.success && result.action === "reject",
          ).length,
          error_count: [...results.values()].filter((result) => !result.success).length,
        },
      };
    }),
  confirmAllMerges: () =>
    set((s) => {
      const decisions: Record<string, "confirm" | "reject"> = {};
      for (const id of Object.keys(s.mergeDecisions)) {
        decisions[id] = "confirm";
      }
      return { mergeDecisions: decisions };
    }),
  rejectAllMerges: () =>
    set((s) => {
      const decisions: Record<string, "confirm" | "reject"> = {};
      for (const id of Object.keys(s.mergeDecisions)) {
        decisions[id] = "reject";
      }
      return { mergeDecisions: decisions };
    }),

  // Batch
  setBatchInput: (batchInput) => set({ batchInput }),

  // Reset
  reset: () =>
    set({
      mode: null,
      currentStep: 0,
      singleInput: DEFAULT_SINGLE_INPUT,
      bulkInput: DEFAULT_BULK_INPUT,
      batchInput: null,
      bulkColumns: null,
      bulkMapping: null,
      bulkPreview: null,
      workflowId: null,
      progress: null,
      singleResult: null,
      mergeCandidates: [],
      mergeDecisions: {},
      mergeOutcomes: null,
    }),
}));
