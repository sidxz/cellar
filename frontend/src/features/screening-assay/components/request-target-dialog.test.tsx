import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { TARGETS_KEY } from "../hooks/use-targets";
import { RequestTargetDialog } from "./request-target-dialog";

const customInstance = vi.fn();
vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/shared/lib/api/custom-instance")>()),
  customInstance: (...args: unknown[]) => customInstance(...args),
}));

// The organism picker is BioPortal-backed; a button stands in for picking a term.
vi.mock("@/shared/components/ontology-search-input", () => ({
  OntologySearchInput: ({ onChange, id }: { onChange: (t: unknown[]) => void; id?: string }) => (
    <button
      id={id}
      type="button"
      onClick={() =>
        onChange([
          {
            term_id: "http://purl.bioontology.org/ontology/NCBITAXON/9606",
            label: "Homo sapiens",
            ontology_source: "NCBITAXON",
            uri: null,
          },
        ])
      }
    >
      pick human
    </button>
  ),
}));

const HERG = {
  id: "t-new",
  workspace_id: "ws",
  name: "hERG",
  target_type: "single_protein",
  organism: "Homo sapiens",
  chembl_id: "CHEMBL240",
};

function renderDialog(onCreated = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(TARGETS_KEY, []);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  render(<RequestTargetDialog open onOpenChange={vi.fn()} onCreated={onCreated} />, { wrapper });
  return { onCreated, qc };
}

describe("RequestTargetDialog", () => {
  it("names the organism picker by its label", () => {
    renderDialog();
    expect(screen.getByLabelText("Organism")).toHaveTextContent("pick human");
  });

  it("submits the request and hands back the created target", async () => {
    customInstance.mockResolvedValue(HERG);
    const { onCreated, qc } = renderDialog();

    const submit = screen.getByRole("button", { name: /request target/i });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: "hERG" } });
    fireEvent.change(screen.getByLabelText(/uniprot accession or entry name/i), {
      target: { value: "Q12809" },
    });
    fireEvent.click(screen.getByLabelText("Organism"));
    fireEvent.change(screen.getByLabelText(/chembl id/i), { target: { value: "CHEMBL240" } });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(HERG));
    expect(customInstance).toHaveBeenCalledWith({
      url: "/api/v1/targets/request",
      method: "POST",
      data: {
        name: "hERG",
        target_type: "single_protein",
        organism_term_id: "http://purl.bioontology.org/ontology/NCBITAXON/9606",
        organism_label: "Homo sapiens",
        chembl_id: "CHEMBL240",
        protein_identifier: "Q12809",
      },
    });
    // The picker can show the new target at once, before the refetch lands.
    expect(qc.getQueryData(TARGETS_KEY)).toEqual([HERG]);
  });

  it("needs the protein for a single-protein target", () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: "hERG" } });
    fireEvent.click(screen.getByLabelText("Organism"));
    expect(screen.getByRole("button", { name: /request target/i })).toBeDisabled();
  });

  it("shows ProtCellar's refusal and keeps the dialog open", async () => {
    const { ApiError } = await import("@/shared/lib/api/custom-instance");
    customInstance.mockRejectedValueOnce(
      new ApiError("API error: 403 — (403) no", 403, {
        error: "AuthorizationError",
        message: "You need editor access in ProtCellar",
        detail: "(403) no",
      }),
    );
    const { onCreated } = renderDialog();
    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: "hERG" } });
    fireEvent.change(screen.getByLabelText(/uniprot accession or entry name/i), {
      target: { value: "Q12809" },
    });
    fireEvent.click(screen.getByLabelText("Organism"));
    fireEvent.click(screen.getByRole("button", { name: /request target/i }));

    expect(await screen.findByText("You need editor access in ProtCellar")).toBeInTheDocument();
    expect(onCreated).not.toHaveBeenCalled();
  });
});
