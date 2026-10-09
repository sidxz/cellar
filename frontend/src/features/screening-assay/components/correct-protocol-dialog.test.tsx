import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { Protocol } from "../types";
import { CorrectProtocolDialog } from "./correct-protocol-dialog";

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
  if (!Element.prototype.hasPointerCapture)
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = vi.fn();
});

const correct = vi.fn();
const preview = vi.hoisted(() => ({
  name: "M. smegmatis growth inhibition [resazurin]",
  base: "M. smegmatis growth inhibition",
  missing: [],
  missing_labels: [],
  clash: null,
  siblings: [],
  needs_discriminator: false,
  discriminator_error: null,
  discriminator_in_pattern: false,
}));

vi.mock("../hooks/use-protocols", () => ({
  useCorrectProtocol: () => ({ mutate: correct, isPending: false }),
}));
vi.mock("../hooks/use-protocol-name-preview", () => ({
  useProtocolNamePreview: () => ({ data: preview, isFetching: false }),
  useDiscriminatorSuggestions: () => [],
}));
vi.mock("../hooks/use-protocol-facet-slots", () => ({ useProtocolFacetSlots: () => [] }));
const direct = vi.hoisted(() => ({
  data: [{ id: "t1", name: "PptT", target_type: "single_protein", is_direct: true, run_count: 0 }],
}));
vi.mock("../hooks/use-protocol-targets", () => ({ useProtocolTargets: () => direct }));
vi.mock("./target-multi-select", () => ({
  TargetMultiSelect: ({ onChange }: { onChange: (ids: string[]) => void }) => (
    <button type="button" onClick={() => onChange([])}>
      remove all targets
    </button>
  ),
}));
vi.mock("./protocol-category-input", () => ({ ProtocolCategoryInput: () => null }));
vi.mock("@/features/workspace-config/hooks/use-protocol-categories", () => ({
  useProtocolCategories: () => ({ data: [] }),
}));

const protocol = {
  id: "p1",
  code: "PRT-00001",
  name: "M. tuberculosis growth inhibition [resazurin]",
  status: "active",
  category: "Growth inhibition",
  discriminator: "resazurin",
  targets: [],
  ontology_annotations: {},
  condition_definitions: [
    {
      id: "c1",
      name: "Incubation time",
      data_type: "numeric",
      unit: "h",
      pick_list_values: null,
      fixed_value: "72",
    },
  ],
} as unknown as Protocol;

describe("CorrectProtocolDialog", () => {
  it("a changed assay leads to a new protocol", () => {
    const onNewAssay = vi.fn();
    render(
      <CorrectProtocolDialog
        protocol={protocol}
        open
        onOpenChange={() => {}}
        onNewAssay={onNewAssay}
      />,
    );
    fireEvent.click(screen.getByLabelText(/the assay changed/i));
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    fireEvent.click(screen.getByRole("button", { name: /create new protocol from this one/i }));
    expect(onNewAssay).toHaveBeenCalled();
  });

  it("a correction needs a reason before it can be saved", () => {
    render(<CorrectProtocolDialog protocol={protocol} open onOpenChange={() => {}} />);
    fireEvent.click(screen.getByLabelText(/correction: it was always this/i));
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    const save = screen.getByRole("button", { name: /save correction/i });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/reason/i), {
      target: { value: "Strain was misrecorded" },
    });
    expect(save).toBeEnabled();
  });

  it("a cancelled session's target edits do not carry into the next correction", () => {
    correct.mockReset();
    const { rerender } = render(
      <CorrectProtocolDialog protocol={protocol} open onOpenChange={() => {}} />,
    );
    fireEvent.click(screen.getByLabelText(/correction: it was always this/i));
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    fireEvent.click(screen.getByRole("button", { name: "remove all targets" }));
    rerender(<CorrectProtocolDialog protocol={protocol} open={false} onOpenChange={() => {}} />);
    rerender(<CorrectProtocolDialog protocol={protocol} open onOpenChange={() => {}} />);
    fireEvent.click(screen.getByLabelText(/correction: it was always this/i));
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    fireEvent.change(screen.getByLabelText(/reason/i), { target: { value: "Typo in category" } });
    fireEvent.click(screen.getByRole("button", { name: /save correction/i }));
    expect(correct).toHaveBeenCalledTimes(1);
    expect(correct.mock.calls[0][0]).not.toHaveProperty("target_ids");
    expect(correct.mock.calls[0][0]).not.toHaveProperty("condition_fixed_values");
  });

  it("corrects a condition's fixed value", () => {
    correct.mockReset();
    render(<CorrectProtocolDialog protocol={protocol} open onOpenChange={() => {}} />);
    fireEvent.click(screen.getByLabelText(/correction: it was always this/i));
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    const fixed = screen.getByLabelText("Incubation time (h)");
    expect(fixed).toHaveValue(72);
    fireEvent.change(fixed, { target: { value: "48" } });
    fireEvent.change(screen.getByLabelText(/reason/i), { target: { value: "It was 48 h" } });
    fireEvent.click(screen.getByRole("button", { name: /save correction/i }));
    expect(correct.mock.calls[0][0].condition_fixed_values).toEqual({ c1: "48" });
  });
});
