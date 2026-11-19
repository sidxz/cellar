import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import { StepResults } from "./step-results";

const h = vi.hoisted(() => ({ submit: vi.fn() }));
vi.mock("../../hooks/use-registration-wizard-api", () => ({
  useConfirmMerges: () => ({ mutateAsync: h.submit, isPending: false }),
}));
vi.mock("./merge-candidate-card", () => ({
  MergeCandidateCard: ({
    candidate,
    decision,
    onDecisionChange,
  }: {
    candidate: { disclosure_id: string };
    decision: string;
    onDecisionChange: (value: string) => void;
  }) => (
    <input
      type="checkbox"
      aria-label={`Merge ${candidate.disclosure_id}`}
      checked={decision === "confirm"}
      onChange={(event) => onDecisionChange(event.target.checked ? "confirm" : "reject")}
    />
  ),
}));

beforeEach(() => {
  useRegistrationWizard.getState().reset();
  h.submit.mockReset();
});
describe("Bulk merge decisions", () => {
  it("keeps successful decisions and retries only failed decisions", async () => {
    useRegistrationWizard.setState({
      mode: "bulk",
      currentStep: 4,
      workflowId: "job-1",
      progress: {
        bulk_reg_id: "job-1",
        status: "completed",
        total_count: 2,
        registered_count: 0,
        duplicate_count: 0,
        error_count: 0,
        disclosed_count: 0,
        merge_candidate_count: 2,
        conflict_count: 0,
        chunks_processed: 1,
        chunks_total: 1,
        merge_candidates: [],
      },
    });
    useRegistrationWizard.getState().setMergeCandidates(
      ["d1", "d2"].map((id, index) => ({
        disclosure_id: id,
        row_index: index,
        molecule_id: `m-${id}`,
        matched_molecule_id: `existing-${id}`,
      })),
    );
    h.submit.mockResolvedValueOnce({
      results: [
        { disclosure_id: "d1", action: "confirm", success: true },
        { disclosure_id: "d2", action: "reject", success: false, error: "Record is locked" },
      ],
      confirmed_count: 1,
      rejected_count: 0,
      error_count: 1,
    });
    h.submit.mockResolvedValueOnce({
      results: [{ disclosure_id: "d2", action: "reject", success: true }],
      confirmed_count: 0,
      rejected_count: 1,
      error_count: 0,
    });
    render(<StepResults />);
    fireEvent.click(screen.getByRole("checkbox", { name: "Merge d2" }));
    fireEvent.click(screen.getByRole("button", { name: "Apply merge decisions" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Record is locked");
    expect(useRegistrationWizard.getState().currentStep).toBe(4);
    expect(screen.queryByRole("checkbox", { name: "Merge d1" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Apply merge decisions" }));
    await waitFor(() => expect(useRegistrationWizard.getState().currentStep).toBe(5));
    expect(h.submit.mock.calls[1][0]).toEqual({
      decisions: [{ disclosure_id: "d2", action: "reject" }],
    });
    expect(useRegistrationWizard.getState().mergeOutcomes).toMatchObject({
      confirmed_count: 1,
      rejected_count: 1,
      error_count: 0,
    });
  });
});
