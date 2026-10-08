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
vi.mock("../hooks/use-protocol-targets", () => ({ useProtocolTargets: () => ({ data: [] }) }));
vi.mock("./target-multi-select", () => ({ TargetMultiSelect: () => null }));
vi.mock("./protocol-category-input", () => ({ ProtocolCategoryInput: () => null }));

const protocol = {
  id: "p1",
  code: "PRT-00001",
  name: "M. tuberculosis growth inhibition [resazurin]",
  status: "active",
  category: "Growth inhibition",
  discriminator: "resazurin",
  targets: [],
  ontology_annotations: {},
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
});
