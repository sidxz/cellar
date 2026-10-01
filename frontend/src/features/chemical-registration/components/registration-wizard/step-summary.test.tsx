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
    expect(screen.getByText("Added to")).toBeInTheDocument();
    expect(screen.getByText("Kinase, GPCR")).toBeInTheDocument();
  });
});
