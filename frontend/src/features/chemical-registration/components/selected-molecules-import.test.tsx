import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CddMoleculeIdentifierCheck } from "../hooks/use-cdd-molecule-import";
import { SelectedMoleculesImport } from "./selected-molecules-import";

const h = vi.hoisted(() => ({
  check: { mutateAsync: vi.fn(), isPending: false },
}));

vi.mock("../hooks/use-cdd-molecule-import", () => ({
  useCheckCddMoleculeIdentifiers: () => h.check,
}));

// The pasted text is parsed by the server's check; the component only shows what the check
// returns. The page holds the list and the answer, and its own button does the importing.
describe("SelectedMoleculesImport: the list and its check", () => {
  const onChecked = vi.fn();

  /** Holds the list and the answer the way the page does. */
  function Harness({ initialText = "" }: { initialText?: string }) {
    const [text, setText] = useState(initialText);
    const [checked, setChecked] = useState<CddMoleculeIdentifierCheck | null>(null);
    return (
      <SelectedMoleculesImport
        text={text}
        onTextChange={setText}
        checked={checked}
        onChecked={(checkedText, result) => {
          onChecked(checkedText, result);
          setChecked(result);
        }}
      />
    );
  }

  const paste = (text: string) =>
    fireEvent.change(screen.getByLabelText("CDD molecule names or synonyms"), {
      target: { value: text },
    });
  const button = (name: string) => screen.getByRole("button", { name });
  const check = () => fireEvent.click(button("Check names in CDD Vault"));

  beforeEach(() => {
    onChecked.mockReset();
    h.check.mutateAsync.mockReset();
    h.check.mutateAsync.mockResolvedValue({
      found: ["SACC-0001", "SACC-0002"],
      not_found: ["SACC-0099"],
    });
  });

  it("offers nothing to check until something is pasted", () => {
    render(<Harness />);
    expect(button("Check names in CDD Vault")).toBeDisabled();
    paste("  \n ");
    expect(button("Check names in CDD Vault")).toBeDisabled();
  });

  it("shows the list the page already holds", () => {
    render(<Harness initialText="SACC-0001" />);
    expect(screen.getByLabelText("CDD molecule names or synonyms")).toHaveValue("SACC-0001");
    expect(button("Check names in CDD Vault")).toBeEnabled();
  });

  it("asks nothing until Check is pressed", () => {
    render(<Harness />);
    paste("SACC-0001, SACC-0002\nSACC-0099");
    expect(button("Check names in CDD Vault")).toBeEnabled();
    expect(h.check.mutateAsync).not.toHaveBeenCalled();
    expect(onChecked).not.toHaveBeenCalled();
  });

  it("sends the text as pasted, so a name with spaces reaches the check whole", async () => {
    h.check.mutateAsync.mockResolvedValue({ found: ["16:0 CoA"], not_found: ["Palmitoyl CoA"] });
    render(<Harness />);
    paste("16:0 CoA\nPalmitoyl CoA");
    check();

    expect(await screen.findByText("1 of 2 names found in CDD Vault.")).toBeInTheDocument();
    expect(h.check.mutateAsync).toHaveBeenCalledExactlyOnceWith("16:0 CoA\nPalmitoyl CoA");
    expect(screen.getByText("Palmitoyl CoA")).toBeInTheDocument();
  });

  it("reports what was found and lists what was not", async () => {
    render(<Harness />);
    paste("SACC-0001, SACC-0002\nSACC-0099");
    check();

    expect(await screen.findByText("2 of 3 names found in CDD Vault.")).toBeInTheDocument();
    expect(h.check.mutateAsync).toHaveBeenCalledWith("SACC-0001, SACC-0002\nSACC-0099");
    expect(screen.getByText("Not found (1)")).toBeInTheDocument();
    expect(screen.getByText("SACC-0099")).toBeInTheDocument();
  });

  it("hands the page the answer with the text it was asked about, and imports nothing itself", async () => {
    render(<Harness />);
    paste("SACC-0001, SACC-0002\nSACC-0099");
    check();

    await waitFor(() =>
      expect(onChecked).toHaveBeenCalledExactlyOnceWith("SACC-0001, SACC-0002\nSACC-0099", {
        found: ["SACC-0001", "SACC-0002"],
        not_found: ["SACC-0099"],
      }),
    );
    // Check identifiers is its only button: the import is the page's.
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  it("shows why a check failed", async () => {
    h.check.mutateAsync.mockRejectedValue(new Error("Could not connect to CDD Vault"));
    render(<Harness />);
    paste("SACC-0001");
    check();
    await waitFor(() =>
      expect(screen.getByText("Could not connect to CDD Vault")).toBeInTheDocument(),
    );
    expect(onChecked).not.toHaveBeenCalled();
  });
});
