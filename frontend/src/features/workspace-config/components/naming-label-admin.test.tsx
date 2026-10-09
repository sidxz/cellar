import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { NamingLabelAdmin } from "./naming-label-admin";

const create = vi.fn();
const update = vi.fn();
const remove = vi.fn();
const state = vi.hoisted(() => ({
  terms: [
    {
      slot: "organism",
      term_id: "http://purl.bioontology.org/ontology/NCBITAXON/1773",
      term_label: "Mycobacterium tuberculosis",
      ontology_source: "NCBITAXON",
      protocol_count: 119,
      default_short_label: "M. tuberculosis",
      override_id: null,
      override_short_label: null,
    },
    {
      slot: "cell_line",
      term_id: "http://purl.obolibrary.org/obo/CLO_0003703",
      term_label: "HepG2 cell",
      ontology_source: "CLO",
      protocol_count: 3,
      default_short_label: "HepG2",
      override_id: "o1",
      override_short_label: "Hep G2",
    },
  ],
}));

const previewRequests: unknown[] = [];
vi.mock("../hooks/use-naming-changes", () => ({
  usePreviewNamingChange: () => ({
    mutate: (req: unknown, opts?: { onSuccess?: () => void }) => {
      previewRequests.push(req);
      opts?.onSuccess?.();
    },
    data: { changes: [], collisions: [] },
    isPending: false,
  }),
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/admin/naming-labels" }));
vi.mock("../hooks/use-naming-labels", () => ({
  useNamingTermsInUse: () => ({ data: state.terms, isLoading: false }),
  useCreateNamingLabel: () => ({ mutateAsync: create, isPending: false }),
  useUpdateNamingLabel: () => ({ mutateAsync: update, isPending: false }),
  useDeleteNamingLabel: () => ({ mutateAsync: remove, isPending: false }),
}));

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
  Element.prototype.releasePointerCapture = vi.fn();
});

describe("NamingLabelAdmin", () => {
  beforeEach(() => {
    create.mockReset();
    update.mockReset();
    remove.mockReset();
  });

  it("shows the default short label and any override", () => {
    render(<NamingLabelAdmin />);
    const mtb = screen.getByText("Mycobacterium tuberculosis").closest("tr") as HTMLElement;
    expect(within(mtb).getByText("M. tuberculosis")).toBeInTheDocument();
    const hep = screen.getByText("HepG2 cell").closest("tr") as HTMLElement;
    expect(within(hep).getByText("Hep G2")).toBeInTheDocument();
  });

  it("creates an override for a term without one", async () => {
    render(<NamingLabelAdmin />);
    const mtb = screen.getByText("Mycobacterium tuberculosis").closest("tr") as HTMLElement;
    fireEvent.click(within(mtb).getByRole("button", { name: /edit/i }));
    fireEvent.change(screen.getByLabelText("Short label"), { target: { value: "Mtb" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    expect(previewRequests.at(-1)).toMatchObject({ kind: "label", short_label: "Mtb" });
    expect(create).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(create).toHaveBeenCalledWith({
      term_id: "http://purl.bioontology.org/ontology/NCBITAXON/1773",
      term_label: "Mycobacterium tuberculosis",
      ontology_source: "NCBITAXON",
      short_label: "Mtb",
    });
  });

  it("resets an override back to the default", () => {
    render(<NamingLabelAdmin />);
    const hep = screen.getByText("HepG2 cell").closest("tr") as HTMLElement;
    fireEvent.click(within(hep).getByRole("button", { name: /edit/i }));
    fireEvent.click(screen.getByRole("button", { name: /reset to default/i }));
    expect(previewRequests.at(-1)).toMatchObject({ kind: "label", short_label: null });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(remove).toHaveBeenCalledWith("o1");
  });
});
