import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SelectedMoleculesImport, parseIdentifiers } from "./selected-molecules-import";

const h = vi.hoisted(() => ({
  check: { mutateAsync: vi.fn(), isPending: false },
}));

vi.mock("../hooks/use-cdd-molecule-import", () => ({
  useCheckCddMoleculeIdentifiers: () => h.check,
}));

describe("parseIdentifiers", () => {
  it("splits on new lines, commas, spaces and tabs", () => {
    expect(parseIdentifiers("SACC-1\nSACC-2, SACC-3 SACC-4\tSACC-5\r\nSACC-6")).toEqual([
      "SACC-1",
      "SACC-2",
      "SACC-3",
      "SACC-4",
      "SACC-5",
      "SACC-6",
    ]);
  });

  it("ignores blank entries", () => {
    expect(parseIdentifiers("\n\n SACC-1 ,, ,\n\t\nSACC-2\n")).toEqual(["SACC-1", "SACC-2"]);
    expect(parseIdentifiers("  \n ,")).toEqual([]);
  });

  it("ignores repeats, whatever their case, and keeps the first spelling", () => {
    expect(parseIdentifiers("SACC-1\nsacc-1\nSACC-2\nSACC-1")).toEqual(["SACC-1", "SACC-2"]);
  });
});

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

  it("offers nothing to check or import until identifiers are pasted", () => {
    renderIt();
    expect(button("Check identifiers")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Import" })).toBeNull();
  });

  it("counts the pasted identifiers beside the Check button, and asks nothing yet", () => {
    renderIt();
    paste("SACC-0001, SACC-0002\nSACC-0099\nsacc-0001");
    expect(screen.getByText("3 identifiers")).toBeInTheDocument();
    expect(button("Check identifiers")).not.toHaveTextContent("3");
    expect(h.check.mutateAsync).not.toHaveBeenCalled();
  });

  it("reports what was found and lists what was not, without importing", async () => {
    renderIt();
    paste("SACC-0001, SACC-0002\nSACC-0099");
    check();

    expect(await screen.findByText("2 of 3 identifiers found in CDD Vault.")).toBeInTheDocument();
    expect(h.check.mutateAsync).toHaveBeenCalledWith(["SACC-0001", "SACC-0002", "SACC-0099"]);
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
