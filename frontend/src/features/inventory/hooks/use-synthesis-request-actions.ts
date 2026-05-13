import { useState } from "react";
import {
  useSubmitSynthesisRequest,
  useApproveSynthesisRequest,
  useCancelSynthesisRequest,
  useDeleteSynthesisRequest,
  useRejectSynthesisRequest,
  useAssignSynthesisRequest,
  useStartSynthesis,
  useFlagInfeasible,
  useCompleteSynthesis,
  useFulfillSynthesisRequest,
  useFailSynthesis,
  useUpdateSynthesisRequest,
} from "./use-synthesis-requests";

export type SynthesisRequestDialogName =
  | "reject"
  | "assign"
  | "start"
  | "flagInfeasible"
  | "complete"
  | "fulfill"
  | "fail"
  | "edit"
  | "delete";

export interface UseSynthesisRequestActionsReturn {
  /** Currently open dialog, or null when all dialogs are closed. */
  activeDialog: SynthesisRequestDialogName | null;
  openDialog: (name: SynthesisRequestDialogName) => void;
  closeDialog: () => void;
  mutations: {
    submit: ReturnType<typeof useSubmitSynthesisRequest>;
    approve: ReturnType<typeof useApproveSynthesisRequest>;
    cancel: ReturnType<typeof useCancelSynthesisRequest>;
    deleteMutation: ReturnType<typeof useDeleteSynthesisRequest>;
    reject: ReturnType<typeof useRejectSynthesisRequest>;
    assign: ReturnType<typeof useAssignSynthesisRequest>;
    start: ReturnType<typeof useStartSynthesis>;
    flagInfeasible: ReturnType<typeof useFlagInfeasible>;
    complete: ReturnType<typeof useCompleteSynthesis>;
    fulfill: ReturnType<typeof useFulfillSynthesisRequest>;
    fail: ReturnType<typeof useFailSynthesis>;
    update: ReturnType<typeof useUpdateSynthesisRequest>;
  };
}

export function useSynthesisRequestActions(): UseSynthesisRequestActionsReturn {
  const [activeDialog, setActiveDialog] =
    useState<SynthesisRequestDialogName | null>(null);

  const openDialog = (name: SynthesisRequestDialogName) =>
    setActiveDialog(name);
  const closeDialog = () => setActiveDialog(null);

  const submit = useSubmitSynthesisRequest();
  const approve = useApproveSynthesisRequest();
  const cancel = useCancelSynthesisRequest();
  const deleteMutation = useDeleteSynthesisRequest();
  const reject = useRejectSynthesisRequest();
  const assign = useAssignSynthesisRequest();
  const start = useStartSynthesis();
  const flagInfeasible = useFlagInfeasible();
  const complete = useCompleteSynthesis();
  const fulfill = useFulfillSynthesisRequest();
  const fail = useFailSynthesis();
  const update = useUpdateSynthesisRequest();

  return {
    activeDialog,
    openDialog,
    closeDialog,
    mutations: {
      submit,
      approve,
      cancel,
      deleteMutation,
      reject,
      assign,
      start,
      flagInfeasible,
      complete,
      fulfill,
      fail,
      update,
    },
  };
}
