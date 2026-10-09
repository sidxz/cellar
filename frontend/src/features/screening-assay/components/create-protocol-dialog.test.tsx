import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
const { ORGANISM_BASED, CELL_BASED } = vi.hoisted(() => {
  const bao = (code: string, label: string) => ({
    term_id: `http://www.bioassayontology.org/bao#${code}`,
    label,
    ontology_source: "BAO",
    uri: null,
  });
  return {
    ORGANISM_BASED: bao("BAO_0000218", "organism-based format"),
    CELL_BASED: bao("BAO_0000219", "cell based format"),
  };
});
const state = vi.hoisted(() => ({
  preview: null as unknown,
  mutate: vi.fn(),
  realPreview: false,
  extraForms: [] as unknown[],
  draft: null as unknown,
}));
state.preview = incomplete;
afterEach(() => {
  state.preview = incomplete;
  state.realPreview = false;
  state.extraForms = [];
  state.mutate.mockReset();
});

// The preview is canned, unless a test runs the real hook against the canned server response.
vi.mock("../hooks/use-protocol-name-preview", async (importOriginal) => {
  const real = await importOriginal<typeof import("../hooks/use-protocol-name-preview")>();
  const canned = (draft: unknown) => {
    state.draft = draft;
    return { data: state.preview, isFetching: false };
  };
  return {
    useProtocolNamePreview: (draft: Parameters<typeof real.useProtocolNamePreview>[0]) =>
      (state.realPreview ? real.useProtocolNamePreview : canned)(draft),
    useDiscriminatorSuggestions: () => [],
  };
});
vi.mock("@/shared/lib/api/custom-instance", () => ({
  API_V1: "/api/v1",
  customInstance: async () => state.preview,
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
      ["strain", "Strain", ""],
    ].map(([name, label, source]) => ({
      id: `std:${name}`,
      name,
      label,
      ontology_sources: source ? [source] : [],
      root_concept_id: null,
      allow_free_text: true,
      is_required: false,
    })),
}));
vi.mock("@/shared/components/ontology-search-input", () => ({
  // A plain input standing in for the picker: typing a label picks that one term.
  OntologySearchInput: ({
    value,
    onChange,
    placeholder,
  }: {
    value: { label: string }[];
    onChange: (terms: unknown[]) => void;
    placeholder?: string;
  }) => (
    <input
      placeholder={placeholder}
      value={value.map((t) => t.label).join(", ")}
      onChange={(e) =>
        onChange([
          { term_id: e.target.value, label: e.target.value, ontology_source: "BAO", uri: null },
        ])
      }
    />
  ),
}));
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
        condition_templates: [{ name: "Incubation time", data_type: "numeric", unit: "h" }],
        ontology_defaults: [{ slot_name: "assay_format", terms: [ORGANISM_BASED] }],
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
        ontology_defaults: [{ slot_name: "assay_format", terms: [ORGANISM_BASED] }],
      },
      {
        id: "f3",
        workspace_id: "w1",
        name: "CC50",
        category_id: "c-cy",
        is_default: true,
        assay_format_from_target: false,
        version: 1,
        readout_templates: [{ name: "CC50", data_type: "numeric", unit: "µM" }],
        condition_templates: [{ name: "Cell density", data_type: "numeric", unit: "cells/well" }],
        ontology_defaults: [{ slot_name: "assay_format", terms: [CELL_BASED] }],
      },
      ...state.extraForms,
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
      { id: "c-cy", label: "Cytotoxicity", name_pattern: "{cell_line} cytotoxicity" },
      { id: "c-pk", label: "Pharmacokinetics", name_pattern: "{organism?} pharmacokinetics" },
      {
        id: "c-pf",
        label: "Parasite growth inhibition",
        name_pattern: "{organism} {strain?} growth inhibition",
      },
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
      {[
        "Growth inhibition",
        "Enzyme inhibition",
        "Detection interference",
        "Solubility",
        "Cytotoxicity",
        "Pharmacokinetics",
        "Parasite growth inhibition",
      ].map((c) => (
        <option key={c} value={c}>
          {c}
        </option>
      ))}
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
const complete = {
  ...incomplete,
  name: "Some name",
  base: "Some name",
  missing: [],
  missing_labels: [],
};
/** Clicks Create and returns the payload sent. */
const submit = async () => {
  fireEvent.click(screen.getByRole("button", { name: "Create Protocol" }));
  await waitFor(() => expect(state.mutate).toHaveBeenCalled());
  return state.mutate.mock.calls[0][0];
};

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

  it("shows an optional slot of the pattern under the category, once, marked optional", () => {
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Pharmacokinetics");
    expect(labels().slice(0, 2)).toEqual(["Category", "Organism (optional)"]);
    openMoreDetails();
    expect(labels().filter((l) => l?.startsWith("Organism"))).toEqual(["Organism (optional)"]);
    expect(labels()).toContain("Cell line");
  });

  it("shows the organism and an optional strain inline when the pattern names a strain", () => {
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Parasite growth inhibition");
    expect(labels().slice(0, 3)).toEqual(["Category", "Organism", "Strain (optional)"]);
    expect(screen.getByPlaceholderText("Type a strain or pick one used here")).toBeInTheDocument();
  });

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

  it("links the Discriminator label to its input", () => {
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Detection interference");
    expect(screen.getByLabelText("Discriminator")).toBe(
      screen.getByPlaceholderText("Part of this category's name"),
    );
  });

  it("explains a discriminator the pattern requires as part of the category's name", () => {
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Detection interference");
    expect(
      screen.getByText("Part of this category's name, so every protocol in it needs one."),
    ).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Part of this category's name")).toBeInTheDocument();
    expect(screen.queryByText(/Only needed when another protocol/)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/resazurin/)).not.toBeInTheDocument();

    // An optional or trailing discriminator keeps the usual guidance.
    pickCategory("Solubility");
    fireEvent.click(screen.getByRole("button", { name: /method or condition/ }));
    expect(screen.getByText(/Only needed when another protocol/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/resazurin/)).toBeInTheDocument();
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

  it("offers generic forms only for a category without forms of its own", () => {
    state.extraForms = [
      {
        id: "g1",
        workspace_id: "w1",
        name: "Single readout",
        category_id: null,
        is_default: false,
        assay_format_from_target: false,
        version: 1,
        readout_templates: [{ name: "Signal", data_type: "numeric" }],
        condition_templates: [],
        ontology_defaults: [],
      },
    ];
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Growth inhibition");
    expect(screen.getByRole("button", { name: "MIC" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Single readout" })).not.toBeInTheDocument();
    pickCategory("Solubility");
    expect(screen.getByRole("button", { name: "Single readout" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "MIC" })).not.toBeInTheDocument();
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

  it("replaces the format and conditions the last form applied when the category changes", async () => {
    state.preview = complete;
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Growth inhibition");
    pickCategory("Cytotoxicity");
    const payload = await submit();
    expect(payload.form_id).toBe("f3");
    expect(payload.ontology_annotations).toEqual({ assay_format: [CELL_BASED] });
    expect(payload.condition_definitions).toEqual([
      { name: "Cell density", data_type: "numeric", unit: "cells/well" },
    ]);
  });

  it("drops the last form's format and conditions for a form that follows the target", async () => {
    state.preview = complete;
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Growth inhibition");
    pickCategory("Enzyme inhibition");
    const payload = await submit();
    expect(payload.form_id).toBe("f2");
    expect(payload.ontology_annotations).toEqual({});
    expect(payload.condition_definitions).toBeUndefined();
  });

  it("clears what a form applied when Blank is picked", async () => {
    state.preview = complete;
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Growth inhibition");
    fireEvent.click(screen.getByRole("button", { name: "Blank" }));
    const payload = await submit();
    expect(payload.form_id).toBeNull();
    expect(payload.ontology_annotations).toEqual({});
    expect(payload.condition_definitions).toBeUndefined();
  });

  it("keeps a format and conditions the chemist edited when the form changes", async () => {
    state.preview = complete;
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Growth inhibition");
    openMoreDetails();
    const format = screen.getByPlaceholderText("Search BAO...");
    expect(format).toHaveValue("organism-based format");
    fireEvent.change(format, { target: { value: "tissue-based format" } });
    fireEvent.change(screen.getByDisplayValue("Incubation time"), {
      target: { value: "Incubation time (aerobic)" },
    });
    pickCategory("Cytotoxicity");
    const payload = await submit();
    expect(payload.ontology_annotations.assay_format).toMatchObject([
      { label: "tissue-based format" },
    ]);
    expect(payload.condition_definitions).toEqual([
      { name: "Incubation time (aerobic)", data_type: "numeric", unit: "h" },
    ]);
  });

  it("sends a pick-list condition's values from a form, with any the chemist adds", async () => {
    state.preview = complete;
    state.extraForms = [
      {
        id: "ames",
        workspace_id: "w1",
        name: "Ames",
        category_id: "c-sol",
        is_default: true,
        assay_format_from_target: false,
        version: 1,
        readout_templates: [{ name: "Revertants", data_type: "numeric" }],
        condition_templates: [
          { name: "S9", data_type: "pick_list", unit: null, pick_list_values: ["with", "without"] },
        ],
        ontology_defaults: [],
      },
    ];
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Solubility");
    openMoreDetails();
    const box = screen.getByPlaceholderText("Type a value, press Enter");
    fireEvent.change(box, { target: { value: "Both" } });
    fireEvent.keyDown(box, { key: "Enter" });
    const payload = await submit();
    expect(payload.condition_definitions).toEqual([
      {
        name: "S9",
        data_type: "pick_list",
        unit: null,
        pick_list_values: ["with", "without", "Both"],
      },
    ]);
  });

  it("keeps a pick-list condition's values when starting from another protocol", async () => {
    state.preview = complete;
    const prefill = protocol({
      readout_definitions: [readout("Percent inhibition", "numeric")],
      condition_definitions: [
        {
          id: "c1",
          name: "S9",
          data_type: "pick_list",
          unit: null,
          pick_list_values: ["with", "without"],
        },
      ],
    });
    render(<CreateProtocolDialog open onOpenChange={() => {}} prefill={prefill} />);
    openMoreDetails();
    expect(screen.getByText("with")).toBeInTheDocument();
    const payload = await submit();
    expect(payload.condition_definitions).toEqual([
      { name: "S9", data_type: "pick_list", unit: null, pick_list_values: ["with", "without"] },
    ]);
  });

  it("keeps a condition's fixed value when starting from another protocol, and sends one typed beside it", async () => {
    state.preview = complete;
    const prefill = protocol({
      readout_definitions: [readout("Percent inhibition", "numeric")],
      condition_definitions: [
        {
          id: "c1",
          name: "Hypoxia",
          data_type: "pick_list",
          unit: null,
          pick_list_values: ["yes", "no"],
          fixed_value: "yes",
        },
        {
          id: "c2",
          name: "Incubation time",
          data_type: "numeric",
          unit: "h",
          pick_list_values: null,
          fixed_value: null,
        },
      ],
    });
    render(<CreateProtocolDialog open onOpenChange={() => {}} prefill={prefill} />);
    openMoreDetails();
    fireEvent.change(screen.getAllByLabelText("Fixed for this protocol")[1], {
      target: { value: "72" },
    });
    const payload = await submit();
    expect(payload.condition_definitions).toEqual([
      {
        name: "Hypoxia",
        data_type: "pick_list",
        unit: null,
        pick_list_values: ["yes", "no"],
        fixed_value: "yes",
      },
      { name: "Incubation time", data_type: "numeric", unit: "h", fixed_value: "72" },
    ]);
  });

  it("suggests the protocol's fixed condition values as discriminators", () => {
    state.preview = complete;
    const prefill = protocol({
      readout_definitions: [readout("Percent inhibition", "numeric")],
      condition_definitions: [
        {
          id: "c1",
          name: "Oxygen",
          data_type: "pick_list",
          unit: null,
          pick_list_values: ["Hypoxia", "Normoxia"],
          fixed_value: "Hypoxia",
        },
        {
          id: "c2",
          name: "Incubation time",
          data_type: "numeric",
          unit: "h",
          pick_list_values: null,
          fixed_value: "72",
        },
        {
          id: "c3",
          name: "Plate",
          data_type: "text",
          unit: null,
          pick_list_values: null,
          fixed_value: null,
        },
      ],
    });
    render(<CreateProtocolDialog open onOpenChange={() => {}} prefill={prefill} />);
    fireEvent.click(screen.getByRole("button", { name: /method or condition/ }));
    expect(screen.getByRole("button", { name: "Hypoxia" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Normoxia" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "72 h" }));
    expect(screen.getByLabelText("Discriminator (optional)")).toHaveValue("72 h");
  });

  it("moves a concentration out of a readout name into the Test concentration condition", async () => {
    state.preview = complete;
    const prefill = protocol({
      readout_definitions: [readout("% inhibition at 2 µM", "numeric")],
    });
    render(<CreateProtocolDialog open onOpenChange={() => {}} prefill={prefill} />);
    expect(screen.getByText("Test concentration belongs in a condition")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    expect(screen.queryByText("Test concentration belongs in a condition")).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText("e.g., % Inhibition")).toHaveValue("% inhibition");
    const payload = await submit();
    expect(payload.readout_definitions[0].name).toBe("% inhibition");
    expect(payload.condition_definitions).toEqual([
      { name: "Test concentration", data_type: "numeric", unit: "µM", fixed_value: "2" },
    ]);
  });

  it("will not create a protocol whose fixed pick is not one of its values", () => {
    state.preview = complete;
    const prefill = protocol({
      readout_definitions: [readout("Percent inhibition", "numeric")],
      condition_definitions: [
        {
          id: "c1",
          name: "Hypoxia",
          data_type: "pick_list",
          unit: null,
          pick_list_values: ["yes", "no"],
          fixed_value: "maybe",
        },
      ],
    });
    render(<CreateProtocolDialog open onOpenChange={() => {}} prefill={prefill} />);
    openMoreDetails();
    expect(screen.getByRole("button", { name: "Create Protocol" })).toBeDisabled();
  });

  it("will not create a protocol whose pick-list condition has no values", () => {
    state.preview = complete;
    const prefill = protocol({
      readout_definitions: [readout("Percent inhibition", "numeric")],
      condition_definitions: [
        { id: "c1", name: "S9", data_type: "pick_list", unit: null, pick_list_values: null },
      ],
    });
    render(<CreateProtocolDialog open onOpenChange={() => {}} prefill={prefill} />);
    openMoreDetails();
    expect(screen.getByText("Add at least one value.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create Protocol" })).toBeDisabled();
  });

  it("reopens clean after a create: no name and no clash until a category is picked", async () => {
    state.realPreview = true;
    const named = { ...complete, name: "M. tuberculosis growth inhibition" };
    state.preview = named;
    state.mutate.mockImplementation((_body, opts: { onSuccess: (p: unknown) => void }) =>
      opts.onSuccess({ id: "p-new" }),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const dialog = (open: boolean) => (
      <QueryClientProvider client={qc}>
        <CreateProtocolDialog open={open} onOpenChange={() => {}} />
      </QueryClientProvider>
    );
    const { rerender } = render(dialog(true));
    pickCategory("Growth inhibition");
    expect(await screen.findByText(named.name)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Create Protocol" }));
    await waitFor(() => expect(state.mutate).toHaveBeenCalled());
    // As after a real create: the name is now taken, and the create invalidates ["protocols"].
    state.preview = {
      ...named,
      clash: { protocol_id: "p-new", code: "PRT-00031", name: named.name },
    };
    await act(() => qc.invalidateQueries({ queryKey: ["protocols"] }));
    rerender(dialog(false));
    await act(() => new Promise((r) => setTimeout(r, 400))); // past the preview debounce
    rerender(dialog(true));

    expect(screen.getByRole("combobox", { name: "Category" })).toHaveValue("");
    expect(screen.getByText("Pick a category to see the name.")).toBeInTheDocument();
    expect(screen.queryByText(named.name)).not.toBeInTheDocument();
    expect(screen.queryByText(/already has this exact name/)).not.toBeInTheDocument();
  });

  it("previews the name with the form it starts from", () => {
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Enzyme inhibition");
    expect(state.draft).toMatchObject({ category: "Enzyme inhibition", form_id: "f2" });
    fireEvent.click(screen.getByRole("button", { name: "Blank" }));
    expect(state.draft).toMatchObject({ form_id: null });
  });

  it("gives conditions the chemist emptied to the next form", async () => {
    state.preview = complete;
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Growth inhibition");
    openMoreDetails();
    fireEvent.click(screen.getByRole("button", { name: "Remove condition" }));
    pickCategory("Cytotoxicity");
    expect((await submit()).condition_definitions).toEqual([
      { name: "Cell density", data_type: "numeric", unit: "cells/well" },
    ]);
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

  it("refuses a nickname that is the protocol's own name", async () => {
    state.preview = { ...complete, name: "M. abscessus growth inhibition" };
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Growth inhibition");
    const nickname = screen.getByLabelText("Also known as");
    fireEvent.change(nickname, { target: { value: " m. abscessus GROWTH inhibition " } });
    fireEvent.keyDown(nickname, { key: "Enter" });
    expect(screen.getByText(/already the protocol's name/)).toBeInTheDocument();
    expect(nickname).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByRole("button", { name: /^Remove / })).not.toBeInTheDocument();

    fireEvent.change(nickname, { target: { value: "Mabs MIC" } });
    expect(screen.queryByText(/already the protocol's name/)).not.toBeInTheDocument();
    fireEvent.keyDown(nickname, { key: "Enter" });
    expect((await submit()).nicknames).toEqual(["Mabs MIC"]);
  });

  it("sends references added under More details, normalized", async () => {
    state.preview = complete;
    render(<CreateProtocolDialog open onOpenChange={() => {}} />);
    pickCategory("Growth inhibition");
    openMoreDetails();
    const value = screen.getByLabelText("Reference value");
    fireEvent.change(value, { target: { value: "doi:10.1021/jm901137j" } });
    fireEvent.keyDown(value, { key: "Enter" });
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "10.1021/jm901137j" })).toHaveAttribute(
        "href",
        "https://doi.org/10.1021/jm901137j",
      ),
    );
    expect((await submit()).references).toEqual([{ kind: "doi", value: "10.1021/jm901137j" }]);
  });

  it("starts from another protocol with its paper-level references, no nicknames and no discriminator", async () => {
    state.preview = complete;
    const prefill = protocol({
      discriminator: "FP",
      aliases: [{ label: "MABA", kind: "nickname" }],
      references: [
        { kind: "doi", value: "10.1021/jm901137j" },
        { kind: "chembl_assay", value: "CHEMBL1054500" },
      ],
      readout_definitions: [readout("Percent inhibition", "numeric")],
    });
    render(<CreateProtocolDialog open onOpenChange={() => {}} prefill={prefill} />);
    const payload = await submit();
    expect(payload.references).toEqual([{ kind: "doi", value: "10.1021/jm901137j" }]);
    expect(payload.nicknames).toEqual([]);
    expect(payload.discriminator).toBeNull();
  });

  it("focuses the discriminator when starting from another protocol", async () => {
    state.preview = { ...complete, siblings: [{ protocol_id: "s1", code: "PRT-1", name: "n" }] };
    const prefill = protocol({ category: "Detection interference" });
    render(<CreateProtocolDialog open onOpenChange={() => {}} prefill={prefill} />);
    await waitFor(() => expect(screen.getByLabelText("Discriminator")).toHaveFocus());
  });

  it("focuses the strain when the pattern names one and no discriminator is shown", async () => {
    const prefill = protocol({ category: "Parasite growth inhibition" });
    render(<CreateProtocolDialog open onOpenChange={() => {}} prefill={prefill} />);
    await waitFor(() =>
      expect(screen.getByPlaceholderText("Type a strain or pick one used here")).toHaveFocus(),
    );
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
