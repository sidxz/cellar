import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SelectedMoleculesImport } from "./selected-molecules-import";

const h = vi.hoisted(() => ({
  check: { mutateAsync: vi.fn(), isPending: false },
}));

vi.mock("../hooks/use-cdd-molecule-import", () => ({
  useCheckCddMoleculeIdentifiers: () => h.check,
}));

// The pasted text is parsed by the server's check; the page only shows what the check returns.
describe("SelectedMoleculesImport: check, then import", () => {
  const onImport = vi.fn();

  function renderIt(organizationSelected = true) {
    render(
      <SelectedMoleculesImport
        organizationSelected={organizationSelected}
        isImporting={false}
        onImport={onImport}
      />,
    );
  }

  const paste = (text: string) =>
    fireEvent.change(screen.getByLabelText("Identifiers"), { target: { value: text } });
  const button = (name: string) => screen.getByRole("button", { name });
  const check = () => fireEvent.click(button("Check identifiers"));

  beforeEach(() => {
    onImport.mockReset();
    h.check.mutateAsync.mockReset();
    h.check.mutateAsync.mockResolvedValue({
      found: ["SACC-0001", "SACC-0002"],
      not_found: ["SACC-0099"],
    });
  });

  it("offers nothing to check or import until something is pasted", () => {
    renderIt();
    expect(button("Check identifiers")).toBeDisabled();
    paste("  \n ");
    expect(button("Check identifiers")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Import" })).toBeNull();
  });

  it("says how to separate identifiers", () => {
    renderIt();
    expect(
      screen.getByText("One per line, or separated by commas. Repeats are ignored."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/spaces/)).toBeNull();
  });

  it("asks nothing until Check is pressed", () => {
    renderIt();
    paste("SACC-0001, SACC-0002\nSACC-0099");
    expect(button("Check identifiers")).toBeEnabled();
    expect(h.check.mutateAsync).not.toHaveBeenCalled();
  });

  it("sends the text as pasted, so a name with spaces reaches the check whole", async () => {
    h.check.mutateAsync.mockResolvedValue({ found: ["16:0 CoA"], not_found: ["Palmitoyl CoA"] });
    renderIt();
    paste("16:0 CoA\nPalmitoyl CoA");
    check();

    expect(await screen.findByText("1 of 2 identifiers found in CDD Vault.")).toBeInTheDocument();
    expect(h.check.mutateAsync).toHaveBeenCalledExactlyOnceWith("16:0 CoA\nPalmitoyl CoA");
    expect(screen.getByText("Palmitoyl CoA")).toBeInTheDocument();
  });

  it("reports what was found and lists what was not, without importing", async () => {
    renderIt();
    paste("SACC-0001, SACC-0002\nSACC-0099");
    check();

    expect(await screen.findByText("2 of 3 identifiers found in CDD Vault.")).toBeInTheDocument();
    expect(h.check.mutateAsync).toHaveBeenCalledWith("SACC-0001, SACC-0002\nSACC-0099");
    expect(screen.getByText("Not found (1)")).toBeInTheDocument();
    expect(screen.getByText("SACC-0099")).toBeInTheDocument();
    expect(onImport).not.toHaveBeenCalled();
  });

  it("imports the found ones on the Import press, with the count beside the button", async () => {
    renderIt();
    paste("SACC-0001, SACC-0002\nSACC-0099");
    check();

    const importButton = await screen.findByRole("button", { name: "Import" });
    expect(importButton).toHaveTextContent(/^Import$/);
    expect(screen.getByText("2 found")).toBeInTheDocument();
    fireEvent.click(importButton);

    expect(onImport).toHaveBeenCalledExactlyOnceWith(["SACC-0001", "SACC-0002"], ["SACC-0099"]);
  });

  it("asks for a new check once the list is edited", async () => {
    renderIt();
    paste("SACC-0001");
    check();
    await screen.findByRole("button", { name: "Import" });

    paste("SACC-0001\nSACC-0003");
    expect(screen.queryByRole("button", { name: "Import" })).toBeNull();
  });

  it("will not import before an organization is chosen", async () => {
    renderIt(false);
    paste("SACC-0001");
    check();
    expect(await screen.findByRole("button", { name: "Import" })).toBeDisabled();
    expect(screen.getByText(/Select the originating organization/)).toBeInTheDocument();
  });

  it("will not import when nothing was found", async () => {
    h.check.mutateAsync.mockResolvedValue({ found: [], not_found: ["SACC-0099"] });
    renderIt();
    paste("SACC-0099");
    check();
    expect(await screen.findByRole("button", { name: "Import" })).toBeDisabled();
  });

  it("shows why a check failed", async () => {
    h.check.mutateAsync.mockRejectedValue(new Error("Could not connect to CDD Vault"));
    renderIt();
    paste("SACC-0001");
    check();
    await waitFor(() =>
      expect(screen.getByText("Could not connect to CDD Vault")).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: "Import" })).toBeNull();
  });
});
