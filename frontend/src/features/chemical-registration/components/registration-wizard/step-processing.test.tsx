import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useRegistrationWizard } from "../../hooks/use-registration-wizard";

const idle = { mutateAsync: vi.fn(), isPending: false, isError: false, error: null };
vi.mock("../../hooks/use-registration-wizard-api", () => ({
  useSubmitRegistration: () => idle,
  useStartBulkRegistration: () => idle,
  useBulkRegistrationStatus: () => ({ data: undefined }),
}));
vi.mock("../../hooks/use-disclosures", () => ({ useSubmitDisclosure: () => idle }));
vi.mock("../../hooks/use-molecules", () => ({ useMolecule: () => ({ data: undefined }) }));
vi.mock("@/features/research-organization/hooks/use-projects", () => ({
  useProjects: () => ({ data: [{ id: "p-1", name: "Kinase" }] }),
}));

import { StepProcessing } from "./step-processing";

describe("StepProcessing (single confirm)", () => {
  beforeEach(() => {
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
});
