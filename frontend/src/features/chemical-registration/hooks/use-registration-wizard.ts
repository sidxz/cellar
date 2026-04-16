"use client";

import { create } from "zustand";
import type {
  WizardMode,
  SingleInput,
  BulkInput,
  BulkProgress,
  MergeCandidateRef,
} from "../types/registration-wizard";
import type { RegistrationResponse } from "../types/index";

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
  originatingOrgId: null,
  externalIds: [],
  customFields: {},
  disclosureMode: false,
  moleculeId: null,
  scientistName: "",
  disclosingOrgId: null,
  notes: "",
};

const DEFAULT_BULK_INPUT: BulkInput = {
  file: null,
  fileFormat: "csv",
  parsedRows: [],
  originatingOrgId: null,
};

const DEFAULT_BATCH_INPUT: WizardBatchInput = {
  source: "synthesis",
  amountValue: null,
  amountUnit: "mg",
  purity: null,
  saltEntryId: null,
  saltStoichiometry: 1,
  appearance: null,
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

  // Job tracking
  workflowId: string | null;
  jobStatus: string | null;
  progress: BulkProgress | null;

  // Results
  singleResult: RegistrationResponse | null;
  mergeCandidates: MergeCandidateRef[];
  mergeDecisions: Record<string, "confirm" | "reject">;

  // ─── Actions ──────────────────────────────────────────────────────────────

  setMode: (mode: WizardMode) => void;
  setCurrentStep: (step: number) => void;
  nextStep: () => void;
  prevStep: () => void;

  updateSingleInput: (patch: Partial<SingleInput>) => void;
  updateBulkInput: (patch: Partial<BulkInput>) => void;

  setWorkflowId: (id: string | null) => void;
  setProgress: (progress: BulkProgress | null) => void;
  setSingleResult: (result: RegistrationResponse | null) => void;

  /** Replaces the merge candidate list and initialises all decisions to "confirm". */
  setMergeCandidates: (candidates: MergeCandidateRef[]) => void;
  /** Set the decision for a single disclosure. */
  setMergeDecision: (
    disclosureId: string,
    decision: "confirm" | "reject"
  ) => void;
  /** Mark every candidate as confirmed. */
  confirmAllMerges: () => void;
  /** Mark every candidate as rejected. */
  rejectAllMerges: () => void;

  setBatchInput: (batch: WizardBatchInput | null) => void;

  reset: () => void;
}

// ─── Store implementation ────────────────────────────────────────────────────

export const useRegistrationWizard = create<RegistrationWizardState>()(
  (set, get) => ({
    // Initial state
    mode: null,
    currentStep: 0,
    singleInput: DEFAULT_SINGLE_INPUT,
    bulkInput: DEFAULT_BULK_INPUT,
    batchInput: null,
    workflowId: null,
    jobStatus: null,
    progress: null,
    singleResult: null,
    mergeCandidates: [],
    mergeDecisions: {},

    // Navigation
    setMode: (mode) => set({ mode, currentStep: 0 }),
    setCurrentStep: (step) => set({ currentStep: step }),
    nextStep: () => set((s) => ({ currentStep: s.currentStep + 1 })),
    prevStep: () =>
      set((s) => ({ currentStep: Math.max(0, s.currentStep - 1) })),

    // Input updates
    updateSingleInput: (patch) =>
      set((s) => ({ singleInput: { ...s.singleInput, ...patch } })),
    updateBulkInput: (patch) =>
      set((s) => ({ bulkInput: { ...s.bulkInput, ...patch } })),

    // Job tracking
    setWorkflowId: (workflowId) => set({ workflowId }),
    setProgress: (progress) =>
      set({ progress, jobStatus: progress?.status ?? null }),
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
        workflowId: null,
        jobStatus: null,
        progress: null,
        singleResult: null,
        mergeCandidates: [],
        mergeDecisions: {},
      }),
  })
);
