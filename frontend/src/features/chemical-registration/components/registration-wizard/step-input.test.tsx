import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import { StepInput } from "./step-input";

vi.mock("../discloser-pick", () => ({ DiscloserPick: () => <span>Disclosed by</span> }));
vi.mock("@/shared/hooks/use-current-user", () => ({ useCurrentUser: () => ({ data: undefined }) }));
vi.mock("@/shared/hooks/use-orgs", () => ({ useOrgName: () => () => "" }));
vi.mock("@/shared/hooks/use-workspace-members", () => ({ useMemberNames: () => () => "" }));
vi.mock("@/features/workspace-config/hooks/use-workspace-settings", () => ({
  useWorkspaceSettings: () => ({ data: { registration_rules: {} } }),
}));
vi.mock("@/features/research-organization/components/search/project-filter", () => ({
  ProjectFilter: ({ emptyLabel }: { emptyLabel: string }) => <span>{emptyLabel}</span>,
}));

function renderUpload(file: File | null = null) {
  const state = useRegistrationWizard.getState();
  useRegistrationWizard.setState({
    mode: "bulk",
    bulkInput: { ...state.bulkInput, file },
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <StepInput />
    </QueryClientProvider>,
  );
}
const fileInput = () => document.querySelector('input[type="file"]') as HTMLInputElement;
beforeEach(() => useRegistrationWizard.getState().reset());

describe("Bulk upload", () => {
  it("replaces the dropzone with one file card and removes the selected file cleanly", () => {
    renderUpload(new File(["name\nAspirin"], "compounds.csv", { type: "text/csv" }));
    const upload = screen.getByRole("region", { name: "Upload file" });
    expect(within(upload).getAllByText("compounds.csv")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Replace file" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Match columns" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Remove file" }));
    expect(useRegistrationWizard.getState().bulkInput.file).toBeNull();
    expect(screen.getByRole("button", { name: "Match columns" })).toBeDisabled();
    expect(screen.getByText("Choose a file to continue.")).toBeVisible();
  });

  it("reports rejected file types without replacing an accepted file", async () => {
    const accepted = new File(["name\nAspirin"], "compounds.csv", { type: "text/csv" });
    renderUpload(accepted);
    fireEvent.change(fileInput(), {
      target: { files: [new File(["document"], "notes.pdf", { type: "application/pdf" })] },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("This file type is not supported");
    expect(useRegistrationWizard.getState().bulkInput.file).toBe(accepted);
  });

  it("rejects an empty supported file", async () => {
    renderUpload();
    fireEvent.change(fileInput(), {
      target: { files: [new File([], "empty.csv", { type: "text/csv" })] },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("This file is empty");
    await waitFor(() => expect(useRegistrationWizard.getState().bulkInput.file).toBeNull());
  });
});
