import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import type { RegistrationResponse } from "../../types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("../../hooks/use-registration-wizard-api", () => ({
  useBulkRegistrationItems: () => ({ data: undefined, isLoading: false }),
}));
vi.mock("@/features/research-organization/hooks/use-projects", () => ({
  useProjects: () => ({
    data: [
      { id: "p-1", name: "Kinase" },
      { id: "p-2", name: "GPCR" },
    ],
  }),
}));

import { StepSummary } from "./step-summary";

const result = {
  molecule: { id: "m-1", registration_number: "CC-000001", name: "Cmpd" },
  batch: null,
  action: "registered",
} as unknown as RegistrationResponse;

describe("StepSummary (single)", () => {
  beforeEach(() => {
    const s = useRegistrationWizard.getState();
    useRegistrationWizard.setState({
      mode: "single",
      singleResult: result,
      singleInput: { ...s.singleInput, projectIds: ["p-1", "p-2"] },
    });
  });

  it("names the projects the compound was added to", () => {
    render(<StepSummary />);
    expect(screen.getByText("Kinase, GPCR")).toBeInTheDocument();
  });
});

describe("Bulk registration outcomes", () => {
  const progress = {
    bulk_reg_id: "job-1",
    status: "completed" as const,
    total_count: 5,
    registered_count: 2,
    duplicate_count: 0,
    error_count: 1,
    disclosed_count: 0,
    merge_candidate_count: 2,
    conflict_count: 0,
    chunks_processed: 1,
    chunks_total: 1,
    merge_candidates: [],
  };
  beforeEach(() => {
    useRegistrationWizard.getState().reset();
    useRegistrationWizard.setState({ mode: "bulk", progress });
  });
  it("shows a partial result and does not describe candidates as completed merges", () => {
    render(<StepSummary />);
    expect(screen.getByText("Registration finished with issues")).toBeVisible();
    expect(screen.getByText("Merge candidates").nextElementSibling).toHaveTextContent("2");
    expect(screen.queryByText("Merges confirmed")).toBeNull();
  });
  it("counts confirmed and rejected decisions from their actual responses", () => {
    useRegistrationWizard.getState().setMergeOutcomes({
      results: [
        { disclosure_id: "d1", action: "confirm", success: true },
        { disclosure_id: "d2", action: "reject", success: true },
      ],
      confirmed_count: 1,
      rejected_count: 1,
      error_count: 0,
    });
    render(<StepSummary />);
    expect(screen.getByText("Merges confirmed").nextElementSibling).toHaveTextContent("1");
    expect(screen.getByText("Merges rejected").nextElementSibling).toHaveTextContent("1");
  });
  it("does not show success for a failed job with zero row errors", () => {
    useRegistrationWizard.setState({ progress: { ...progress, status: "failed", error_count: 0 } });
    render(<StepSummary />);
    expect(screen.getByText("Registration failed")).toBeVisible();
    expect(screen.queryByText("Registration complete")).toBeNull();
  });
});
