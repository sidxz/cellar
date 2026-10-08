import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { Protocol } from "../types";
import { CreateProtocolDialog } from "./create-protocol-dialog";

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
  if (!Element.prototype.hasPointerCapture)
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = vi.fn();
});

const preview = vi.hoisted(() => ({
  name: "(organism) growth inhibition",
  base: "(organism) growth inhibition",
  missing: ["organism"],
  missing_labels: ["an organism"],
  clash: null,
  siblings: [],
  needs_discriminator: false,
  discriminator_error: null,
  discriminator_in_pattern: false,
}));

vi.mock("../hooks/use-protocol-name-preview", () => ({
  useProtocolNamePreview: () => ({ data: preview, isFetching: false }),
  useDiscriminatorSuggestions: () => [],
}));
vi.mock("../hooks/use-protocols", () => ({
  useCreateProtocol: () => ({ mutate: vi.fn(), isPending: false }),
  useProtocols: () => ({ data: [] }),
}));
vi.mock("../hooks/use-targets", () => ({ useTargets: () => ({ data: [] }) }));
vi.mock("../hooks/use-protocol-projects", () => ({
  useAssignProtocolToProject: () => ({ mutateAsync: vi.fn() }),
}));
vi.mock("../hooks/use-protocol-facet-slots", () => ({ useProtocolFacetSlots: () => [] }));
vi.mock("@/features/research-organization/hooks/use-projects", () => ({
  useProjects: () => ({ data: [] }),
}));
vi.mock("@/features/workspace-config/hooks/use-protocol-forms", () => ({
  useProtocolForms: () => ({ data: [] }),
}));
vi.mock("@/features/workspace-config/hooks/use-protocol-categories", () => ({
  useProtocolCategories: () => ({ data: [{ label: "Growth inhibition" }] }),
}));
vi.mock("./similar-protocols-panel", () => ({ SimilarProtocolsPanel: () => null }));
vi.mock("./vocabulary-autocomplete", () => ({
  VocabularyAutocomplete: ({ value }: { value: string }) => <input readOnly value={value} />,
}));
vi.mock("./target-multi-select", () => ({ TargetMultiSelect: () => null }));

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
    const prefill = {
      id: "p1",
      code: "PRT-00007",
      name: "PptT inhibition [FP]",
      discriminator: "FP",
      protocol_type: "biochemical",
      category: "Enzyme inhibition",
      description: "old",
      dose_unit: "uM",
      targets: [],
      readout_definitions: [
        {
          name: "Percent inhibition",
          data_type: "numeric",
          unit: "%",
          aggregation: "none",
          normalizations: [],
          is_calculated: false,
          calculation_formula: null,
          display_order: 1,
          pick_list_values: null,
          dose_response_config: null,
        },
      ],
      condition_definitions: [],
      ontology_annotations: null,
    } as unknown as Protocol;
    render(<CreateProtocolDialog open onOpenChange={() => {}} prefill={prefill} />);
    expect(screen.getByText("New protocol from PRT-00007")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Percent inhibition")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("FP")).not.toBeInTheDocument();
  });
});
