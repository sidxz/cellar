import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ProtocolFormAdmin } from "./protocol-form-admin";

const update = vi.fn();
const seed = vi.fn();
const state = vi.hoisted(() => ({
  forms: [
    {
      id: "f1",
      workspace_id: "w1",
      name: "Standard IC50",
      description: null,
      protocol_type: "biochemical",
      is_default: true,
      category_id: "c1",
      assay_format_from_target: true,
      version: 3,
      readout_templates: [
        { name: "Signal", data_type: "numeric", unit: null, normalization: "percent_inhibition" },
        {
          name: "IC50",
          data_type: "dose_response",
          unit: "µM",
          aggregation: "none",
          normalization: "none",
          dose_response_config: { curve_type: "ic50", y_readout_name: "Signal" },
        },
      ],
      condition_templates: [
        { name: "Buffer", data_type: "pick_list", pick_list_values: ["PBS", "HEPES"] },
      ],
      ontology_defaults: [
        {
          slot_name: "detection",
          terms: [
            {
              term_id: "http://www.bioassayontology.org/bao#BAO_0000001",
              label: "fluorescence",
              ontology_source: "BAO",
              uri: null,
            },
          ],
        },
      ],
    },
  ],
}));

vi.mock("next/navigation", () => ({ usePathname: () => "/admin/protocol-forms" }));
vi.mock("../hooks/use-protocol-forms", () => ({
  useProtocolForms: () => ({ data: state.forms, isLoading: false }),
  useCreateProtocolForm: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateProtocolForm: () => ({ mutateAsync: update, isPending: false }),
  useDeleteProtocolForm: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSeedDefaultProtocolForms: () => ({ mutate: seed, isPending: false }),
}));
vi.mock("../hooks/use-protocol-categories", () => ({
  useProtocolCategories: () => ({
    data: [{ id: "c1", label: "Enzyme inhibition", name_pattern: "{target} inhibition" }],
  }),
}));
vi.mock("@/features/screening-assay/hooks/use-protocol-facet-slots", () => ({
  useProtocolFacetSlots: () => [
    {
      id: "std:detection",
      name: "detection",
      label: "Detection method",
      ontology_sources: ["BAO"],
      root_concept_id: null,
      allow_free_text: true,
      is_required: false,
    },
  ],
}));
vi.mock("@/shared/components/ontology-search-input", () => ({ OntologySearchInput: () => null }));
vi.mock("@/shared/hooks/use-units", () => ({ useUnits: () => ({ data: [] }) }));

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn(() => false);
  Element.prototype.releasePointerCapture = vi.fn();
});

describe("ProtocolFormAdmin", () => {
  beforeEach(() => {
    update.mockReset();
    seed.mockReset();
  });

  it("keeps template fields it does not show when saving an edit", async () => {
    render(<ProtocolFormAdmin />);
    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(update).toHaveBeenCalled());
    const sent = update.mock.calls[0][0];
    expect(sent.readout_templates[1].dose_response_config).toEqual({
      curve_type: "ic50",
      y_readout_name: "Signal",
    });
    expect(sent.condition_templates[0].pick_list_values).toEqual(["PBS", "HEPES"]);
    expect(sent.category_id).toBe("c1");
    expect(sent.assay_format_from_target).toBe(true);
    expect(sent.ontology_defaults).toEqual([
      {
        slot_name: "detection",
        terms: [
          {
            term_id: "http://www.bioassayontology.org/bao#BAO_0000001",
            label: "fluorescence",
            ontology_source: "BAO",
            uri: null,
          },
        ],
      },
    ]);
  });

  it("groups forms under their category", () => {
    render(<ProtocolFormAdmin />);
    expect(screen.getByText("Enzyme inhibition")).toBeInTheDocument();
  });

  it("adds the default forms", () => {
    render(<ProtocolFormAdmin />);
    fireEvent.click(screen.getByRole("button", { name: /add default forms/i }));
    expect(seed).toHaveBeenCalled();
  });
});
