import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import type { Protocol } from "../types";
import { CreateProtocolDialog } from "./create-protocol-dialog";

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
  if (!Element.prototype.hasPointerCapture)
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = vi.fn();
});

const incomplete = {
  name: "(organism) growth inhibition",
  base: "(organism) growth inhibition",
  missing: ["organism"],
  missing_labels: ["an organism"],
  clash: null,
  siblings: [],
  needs_discriminator: false,
  discriminator_error: null,
  discriminator_in_pattern: false,
  sibling_renames: [],
};
const state = vi.hoisted(() => ({ preview: null as unknown, mutate: vi.fn() }));
state.preview = incomplete;
afterEach(() => {
  state.preview = incomplete;
  state.mutate.mockReset();
});

vi.mock("../hooks/use-protocol-name-preview", () => ({
  useProtocolNamePreview: () => ({ data: state.preview, isFetching: false }),
  useDiscriminatorSuggestions: () => [],
}));
vi.mock("../hooks/use-protocols", () => ({
  useCreateProtocol: () => ({ mutate: state.mutate, isPending: false }),
  useProtocols: () => ({ data: [] }),
}));
vi.mock("../hooks/use-targets", () => ({ useTargets: () => ({ data: [] }) }));
vi.mock("../hooks/use-protocol-projects", () => ({
  useAssignProtocolToProject: () => ({ mutateAsync: vi.fn() }),
}));
vi.mock("../hooks/use-protocol-facet-slots", () => ({
  useProtocolFacetSlots: () =>
    [
      ["organism", "Organism", "NCBITAXON"],
      ["cell_line", "Cell line", "CLO"],
      ["assay_format", "Assay format", "BAO"],
    ].map(([name, label, source]) => ({
      id: `std:${name}`,
      name,
      label,
      ontology_sources: [source],
      root_concept_id: null,
      allow_free_text: true,
      is_required: false,
    })),
}));
vi.mock("@/shared/components/ontology-search-input", () => ({ OntologySearchInput: () => null }));
vi.mock("@/shared/hooks/use-units", () => ({ useUnits: () => ({ data: [] }) }));
vi.mock("@/features/research-organization/hooks/use-projects", () => ({
  useProjects: () => ({ data: [] }),
}));
vi.mock("@/features/workspace-config/hooks/use-protocol-forms", () => ({
  useProtocolForms: () => ({
    data: [
      {
        id: "f1",
        workspace_id: "w1",
        name: "MIC",
        category_id: "c-gi",
        is_default: true,
        assay_format_from_target: false,
        version: 1,
        readout_templates: [
          {
            name: "MIC",
            data_type: "numeric",
            unit: "µM",
            aggregation: "none",
            normalization: "none",
            is_calculated: false,
          },
        ],
        condition_templates: [],
        ontology_defaults: [],
      },
      {
        id: "f2",
        workspace_id: "w1",
        name: "IC50 dose-response",
        category_id: "c-ei",
        is_default: true,
        assay_format_from_target: true,
        version: 1,
        readout_templates: [{ name: "IC50", data_type: "dose_response", unit: "µM" }],
        condition_templates: [],
        ontology_defaults: [],
      },
    ],
  }),
}));
vi.mock("@/features/workspace-config/hooks/use-protocol-categories", () => ({
  useProtocolCategories: () => ({
    data: [
      { id: "c-gi", label: "Growth inhibition", name_pattern: "{organism} growth inhibition" },
      { id: "c-ei", label: "Enzyme inhibition", name_pattern: "{target} inhibition" },
      {
        id: "c-di",
        label: "Detection interference",
        name_pattern: "{discriminator} interference",
      },
      { id: "c-sol", label: "Solubility", name_pattern: "{discriminator?} solubility" },
    ],
  }),
}));
vi.mock("./protocol-category-input", () => ({
  ProtocolCategoryInput: ({
    value,
    onChange,
  }: {
    value: string;
    onChange: (v: string) => void;
  }) => (
    <select aria-label="Category" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="" />
      {["Growth inhibition", "Enzyme inhibition", "Detection interference", "Solubility"].map(
        (c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ),
      )}
    </select>
  ),
}));
vi.mock("./similar-protocols-panel", () => ({ SimilarProtocolsPanel: () => null }));
vi.mock("./vocabulary-autocomplete", () => ({
  VocabularyAutocomplete: ({
    value,
    onChange,
    placeholder,
  }: {
    value: string;
    onChange: (v: string) => void;
    placeholder?: string;
  }) => (
    <input value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
  ),
}));
vi.mock("./target-multi-select", () => ({ TargetMultiSelect: () => null }));

const pickCategory = (label: string) =>
  fireEvent.change(screen.getByRole("combobox", { name: "Category" }), {
    target: { value: label },
  });
const labels = () =>
  screen.getAllByText((_, el) => el?.tagName === "LABEL").map((l) => l.textContent);
const openMoreDetails = () => fireEvent.click(screen.getByRole("button", { name: /More details/ }));

const protocol = (over: Record<string, unknown> = {}) =>
  ({
    id: "p1",
    code: "PRT-00007",
    name: "x",
    discriminator: null,
    protocol_type: "biochemical",
    category: "Enzyme inhibition",
    description: null,
    dose_unit: "uM",
    targets: [],
    readout_definitions: [],
    condition_definitions: [],
    ontology_annotations: null,
    ...over,
  }) as unknown as Protocol;

const readout = (name: string, data_type: string) => ({
  name,
  data_type,
  unit: "%",
  aggregation: "none",
  normalizations: [],
  is_calculated: false,
  calculation_formula: null,
  display_order: 1,
  pick_list_values: null,
  dose_response_config: null,
});

describe("CreateProtocolDialog", () => {
  it("shows the generated name instead of a name field", () => {
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    expect(screen.queryByRole("textbox", { name: /^name$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/needs an organism/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create Protocol" })).toBeDisabled();
  });

  it("does not label the category optional, since the name needs it", () => {
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    expect(screen.getByText("Category")).toBeInTheDocument();
    expect(screen.queryByText("Category (optional)")).not.toBeInTheDocument();
  });

  it("starts a new assay from an existing protocol's facts", () => {
    const prefill = protocol({
      name: "PptT inhibition [FP]",
      discriminator: "FP",
      description: "old",
      readout_definitions: [readout("Percent inhibition", "numeric")],
    });
    render(<CreateProtocolDialog open onOpenChange={() => {}} prefill={prefill} />);
    expect(screen.getByText("New protocol from PRT-00007")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Percent inhibition")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("FP")).not.toBeInTheDocument();
  });

  it.each([
    ["Growth inhibition", "Organism", "Target"],
    ["Enzyme inhibition", "Target", "Organism"],
  ])(
    "puts %s first and the fact its pattern needs (%s) right under it",
    (category, needed, other) => {
      render(<CreateProtocolDialog open onOpenChange={() => {}} />);
      expect(labels()[0]).toBe("Category");
      pickCategory(category);
      expect(labels().slice(0, 2)).toEqual(["Category", needed]);
      // Facts the pattern does not need wait under More details.
      expect(labels()).not.toContain(other);
      expect(labels()).not.toContain("Cell line");
      openMoreDetails();
      expect(labels()).toContain("Cell line");
    },
  );

  it("asks for a discriminator only when the pattern places it, else one click away", () => {
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Detection interference");
    expect(labels()).toContain("Discriminator");
    expect(screen.queryByRole("button", { name: /method or condition/ })).not.toBeInTheDocument();

    pickCategory("Solubility");
    expect(labels()).not.toContain("Discriminator");
    fireEvent.click(screen.getByRole("button", { name: /method or condition/ }));
    expect(labels()).toContain("Discriminator (optional)");
  });

  it("starts from the category's default form", () => {
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    expect(screen.queryByText("Starts from")).not.toBeInTheDocument();
    pickCategory("Growth inhibition");
    expect(screen.getByText("Starts from")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "MIC" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByDisplayValue("MIC")).toBeInTheDocument();
    expect(screen.queryByText(/Replace your readouts/)).not.toBeInTheDocument();
  });

  it("says the assay format follows the target only when the form does", () => {
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    openMoreDetails();
    pickCategory("Growth inhibition");
    expect(screen.queryByText("Follows the target")).not.toBeInTheDocument();
    // The readouts are still the last form's, so the next form replaces them without asking.
    pickCategory("Enzyme inhibition");
    expect(screen.queryByText(/Replace your readouts/)).not.toBeInTheDocument();
    expect(screen.getByDisplayValue("IC50")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "IC50 dose-response" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByText("Follows the target")).toBeInTheDocument();
  });

  it("hides Dose unit until a readout fits dose-response curves", () => {
    const { unmount } = render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    openMoreDetails();
    expect(screen.getByText("Description")).toBeInTheDocument();
    expect(screen.queryByText("Dose unit")).not.toBeInTheDocument();
    unmount();

    const prefill = protocol({
      readout_definitions: [readout("IC50", "dose_response")],
    });
    render(<CreateProtocolDialog open onOpenChange={() => {}} prefill={prefill} />);
    openMoreDetails();
    expect(screen.getByText("Dose unit")).toBeInTheDocument();
  });

  it("asks before replacing readouts the chemist edited", () => {
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText("e.g., % Inhibition"), {
      target: { value: "Signal" },
    });
    pickCategory("Growth inhibition");
    expect(screen.getByText(/Replace your readouts/)).toBeInTheDocument();
    expect(screen.getByDisplayValue("Signal")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Replace" }));
    expect(screen.getByDisplayValue("MIC")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Signal")).not.toBeInTheDocument();
  });

  it("keeps the chemist's readouts when they say so", () => {
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText("e.g., % Inhibition"), {
      target: { value: "Signal" },
    });
    pickCategory("Growth inhibition");
    fireEvent.click(screen.getByRole("button", { name: "Keep mine" }));
    expect(screen.getByDisplayValue("Signal")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("MIC")).not.toBeInTheDocument();
  });

  it("says a reopened draft was kept and clears it on request", () => {
    const { rerender } = render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    expect(screen.queryByText("Draft kept")).not.toBeInTheDocument();
    pickCategory("Growth inhibition");
    rerender(<CreateProtocolDialog open={false} onOpenChange={() => {}} />);
    rerender(<CreateProtocolDialog open onOpenChange={() => {}} />);
    expect(screen.getByText("Draft kept")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Category" })).toHaveValue("Growth inhibition");
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.queryByText("Draft kept")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Category" })).toHaveValue("");
  });

  it("creates with the form, nicknames and the siblings' discriminators in one save", async () => {
    const sibling = {
      protocol_id: "s1",
      code: "PRT-00004",
      name: "M. tuberculosis growth inhibition",
      discriminator: null,
      status: "active",
      is_locked: false,
    };
    state.preview = {
      ...incomplete,
      name: "M. tuberculosis growth inhibition [REMA]",
      base: "M. tuberculosis growth inhibition",
      missing: [],
      missing_labels: [],
      siblings: [sibling],
    };
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Growth inhibition");
    const nickname = screen.getByLabelText("Also known as");
    fireEvent.change(nickname, { target: { value: "MABA" } });
    fireEvent.keyDown(nickname, { key: "Enter" });
    expect(screen.getByText("MABA")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Discriminator for PRT-00004"), {
      target: { value: "OD600" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create Protocol" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    expect(state.mutate.mock.calls[0][0]).toMatchObject({
      form_id: "f1",
      nicknames: ["MABA"],
      sibling_discriminators: [
        {
          protocol_id: "s1",
          discriminator: "OD600",
          reason: "Distinguish from the new protocol (M. tuberculosis growth inhibition [REMA])",
        },
      ],
    });
  });
});
