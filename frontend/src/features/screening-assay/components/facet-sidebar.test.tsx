import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { FacetGroup } from "../lib/protocol-facets";
import { FacetSidebar } from "./facet-sidebar";

// Radix Checkbox renders as <button role="checkbox">; pointer-event stubs for jsdom.
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn();
  }
});

const model: FacetGroup[] = [
  {
    dimension: "type",
    label: "Type",
    values: [
      { value: "biochemical", label: "Biochemical", count: 2 },
      { value: "cell_based", label: "Cell-Based", count: 1 },
    ],
  },
];

describe("FacetSidebar", () => {
  it("renders facet values with counts and reports toggles", () => {
    const onToggle = vi.fn();
    render(<FacetSidebar model={model} selections={{}} onToggle={onToggle} onClear={vi.fn()} />);
    expect(screen.getByText("Biochemical")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Biochemical"));
    expect(onToggle).toHaveBeenCalledWith("type", "biochemical");
  });

  it("reflects a checked selection", () => {
    render(
      <FacetSidebar
        model={model}
        selections={{ type: new Set(["biochemical"]) }}
        onToggle={vi.fn()}
        onClear={vi.fn()}
      />,
    );
    const checkbox = screen.getByRole("checkbox", { name: /Biochemical/i });
    expect(checkbox).toBeChecked();
  });

  it("gives a short-labelled value its full label by name and on keyboard focus", async () => {
    const organisms: FacetGroup[] = [
      {
        dimension: "organism",
        label: "Organism",
        values: [{ value: "mtb", label: "Mtb", fullLabel: "Mycobacterium tuberculosis", count: 4 }],
      },
    ];
    render(<FacetSidebar model={organisms} selections={{}} onToggle={vi.fn()} onClear={vi.fn()} />);
    const row = screen.getByRole("checkbox", { name: "Mycobacterium tuberculosis" });
    expect(row).toHaveTextContent("Mtb");
    act(() => row.focus());
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Mycobacterium tuberculosis");
  });
});
