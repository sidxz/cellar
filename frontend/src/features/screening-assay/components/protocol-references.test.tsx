import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Protocol, ProtocolReference } from "../types";
import { ProtocolReferencesCard, ReferencesEditor } from "./protocol-references";

const addMutateAsync = vi.fn();
const removeMutate = vi.fn();

vi.mock("../hooks/use-protocols", () => ({
  useAddProtocolReference: () => ({ mutateAsync: addMutateAsync, isPending: false }),
  useRemoveProtocolReference: () => ({ mutate: removeMutate, isPending: false }),
}));

const REFS: ProtocolReference[] = [
  { kind: "chembl_assay", value: "CHEMBL1054500" },
  { kind: "pubchem_aid", value: "1851" },
  { kind: "doi", value: "10.1021/jm901137j" },
  { kind: "pmid", value: "19919034" },
  { kind: "url", value: "https://example.org/assay" },
];

describe("ReferencesEditor", () => {
  it("renders links built only from the fixed templates", () => {
    render(<ReferencesEditor references={REFS} onAdd={vi.fn()} onRemove={vi.fn()} canEdit />);
    const hrefs = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual([
      "https://www.ebi.ac.uk/chembl/explore/assay/CHEMBL1054500",
      "https://pubchem.ncbi.nlm.nih.gov/bioassay/1851",
      "https://doi.org/10.1021/jm901137j",
      "https://pubmed.ncbi.nlm.nih.gov/19919034",
      "https://example.org/assay",
    ]);
    for (const a of screen.getAllByRole("link")) {
      expect(a).toHaveAttribute("rel", "noopener noreferrer");
      expect(a).toHaveAttribute("target", "_blank");
    }
  });

  it("shows an unsafe value as text, never as a link", () => {
    render(
      <ReferencesEditor
        references={[{ kind: "url", value: "javascript:alert(1)" }]}
        onAdd={vi.fn()}
        onRemove={vi.fn()}
        canEdit={false}
      />,
    );
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText("javascript:alert(1)")).toBeInTheDocument();
  });

  it("adds a normalized value of the default kind (DOI)", async () => {
    const onAdd = vi.fn();
    render(<ReferencesEditor references={[]} onAdd={onAdd} onRemove={vi.fn()} canEdit />);
    fireEvent.change(screen.getByLabelText("Reference value"), {
      target: { value: "https://doi.org/10.1021/jm901137j" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add reference" }));
    await waitFor(() =>
      expect(onAdd).toHaveBeenCalledWith({ kind: "doi", value: "10.1021/jm901137j" }),
    );
    await waitFor(() => expect(screen.getByLabelText("Reference value")).toHaveValue(""));
  });

  it("says what is wrong instead of adding an invalid or duplicate value", () => {
    const onAdd = vi.fn();
    render(
      <ReferencesEditor
        references={[{ kind: "doi", value: "10.1021/jm901137j" }]}
        onAdd={onAdd}
        onRemove={vi.fn()}
        canEdit
      />,
    );
    const input = screen.getByLabelText("Reference value");
    fireEvent.change(input, { target: { value: "not a doi" } });
    fireEvent.click(screen.getByRole("button", { name: "Add reference" }));
    expect(screen.getByText("Not a valid DOI")).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "doi:10.1021/jm901137j" } });
    fireEvent.click(screen.getByRole("button", { name: "Add reference" }));
    expect(screen.getByText("Already listed")).toBeInTheDocument();
    expect(onAdd).not.toHaveBeenCalled();
  });

  it("removes a reference", () => {
    const onRemove = vi.fn();
    render(<ReferencesEditor references={REFS} onAdd={vi.fn()} onRemove={onRemove} canEdit />);
    fireEvent.click(screen.getByRole("button", { name: "Remove PMID 19919034" }));
    expect(onRemove).toHaveBeenCalledWith(REFS[3]);
  });
});

describe("ProtocolReferencesCard", () => {
  const protocol = { id: "p-1", references: REFS.slice(0, 1) } as unknown as Protocol;

  beforeEach(() => {
    addMutateAsync.mockReset();
    removeMutate.mockReset();
  });

  it("adds through the API and removes by reference", async () => {
    addMutateAsync.mockResolvedValue({});
    render(<ProtocolReferencesCard protocol={protocol} canEdit />);
    fireEvent.change(screen.getByLabelText("Reference value"), {
      target: { value: "10.1021/jm901137j" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add reference" }));
    await waitFor(() =>
      expect(addMutateAsync).toHaveBeenCalledWith({ kind: "doi", value: "10.1021/jm901137j" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Remove ChEMBL assay CHEMBL1054500" }));
    expect(removeMutate).toHaveBeenCalledWith(REFS[0]);
  });

  it("keeps the typed value when the API refuses it", async () => {
    addMutateAsync.mockRejectedValue(new Error("409"));
    render(<ProtocolReferencesCard protocol={protocol} canEdit />);
    const input = screen.getByLabelText("Reference value");
    fireEvent.change(input, { target: { value: "10.1021/jm901137j" } });
    fireEvent.click(screen.getByRole("button", { name: "Add reference" }));
    await waitFor(() => expect(addMutateAsync).toHaveBeenCalled());
    expect(input).toHaveValue("10.1021/jm901137j");
  });

  it("is read-only without edit rights", () => {
    render(<ProtocolReferencesCard protocol={protocol} canEdit={false} />);
    expect(screen.queryByLabelText("Reference value")).not.toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "https://www.ebi.ac.uk/chembl/explore/assay/CHEMBL1054500",
    );
  });
});
