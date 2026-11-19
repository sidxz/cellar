import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useRegistrationWizard } from "../../hooks/use-registration-wizard";

const idle = { mutateAsync: vi.fn(), isPending: false, isError: false, error: null };
const registerMutate = vi.fn();
const h = vi.hoisted(() => ({ bulkStatus: undefined as Record<string, unknown> | undefined }));
vi.mock("../../hooks/use-registration-wizard-api", () => ({
  useSubmitRegistration: () => ({ ...idle, mutateAsync: registerMutate }),
  useStartBulkRegistration: () => idle,
  useBulkRegistrationStatus: () => ({ data: h.bulkStatus }),
}));
vi.mock("../../hooks/use-disclosures", () => ({ useSubmitDisclosure: () => idle }));
vi.mock("../../hooks/use-molecules", () => ({ useMolecule: () => ({ data: undefined }) }));
vi.mock("@/features/research-organization/hooks/use-projects", () => ({
  useProjects: () => ({ data: [{ id: "p-1", name: "Kinase" }] }),
}));

import { StepProcessing } from "./step-processing";

describe("StepProcessing (single confirm)", () => {
  beforeEach(() => {
    registerMutate.mockReset();
    registerMutate.mockResolvedValue({
      molecule: { id: "m-1" },
      needs_merge_confirmation: false,
    });
    const s = useRegistrationWizard.getState();
    useRegistrationWizard.setState({
      mode: "single",
      singleInput: { ...s.singleInput, name: "Cmpd", projectIds: ["p-1"] },
    });
  });

  it("shows the projects the compound will be added to before confirming", () => {
    render(<StepProcessing />);
    expect(screen.getByText("Projects:")).toBeInTheDocument();
    expect(screen.getByText("Kinase")).toBeInTheDocument();
  });

  it("sends the chosen projects with the registration", async () => {
    render(<StepProcessing />);
    fireEvent.click(screen.getByRole("button", { name: /confirm & register/i }));
    await waitFor(() => expect(registerMutate).toHaveBeenCalledTimes(1));
    expect(registerMutate.mock.calls[0][0].project_ids).toEqual(["p-1"]);
  });
});

describe("Bulk registration recovery", () => {
  it("polls an existing registration without submitting its file again", () => {
    useRegistrationWizard.getState().reset();
    useRegistrationWizard.setState({
      mode: "bulk",
      currentStep: 3,
      workflowId: "bulk-reg-existing",
    });
    idle.mutateAsync.mockClear();
    h.bulkStatus = {
      status: "processing",
      total_count: 10,
      registered_count: 2,
      duplicate_count: 0,
      disclosed_count: 0,
      merge_candidate_count: 0,
      conflict_count: 0,
      error_count: 0,
      merge_candidates: [],
    };
    render(<StepProcessing />);
    expect(idle.mutateAsync).not.toHaveBeenCalled();
    expect(screen.getByRole("progressbar", { name: "Registration progress" })).toHaveAttribute(
      "value",
      "20",
    );
    expect(screen.getByText("2 of 10 rows processed")).toBeVisible();
    h.bulkStatus = undefined;
  });
});
