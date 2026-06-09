import type { Collection, CollectionType } from "@/features/research-organization/types";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { CollectionMultiSelect } from "./collection-multi-select";

// Radix Popover/Command items need pointer-event stubs in jsdom (mirrors
// target-multi-select.test.tsx).
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

const collection = (id: string, name: string, type: CollectionType): Collection => ({
  id,
  workspace_id: "ws-1",
  name,
  created_by: "u-1",
  molecule_count: 0,
  visibility: "private",
  type,
  version: 1,
});

// `Zeta` (library) and `Beta` (library) sort before `Alpha` (generic) despite
// alphabetics, because Library-typed collections are screening-relevant and
// floated to the top. Canned out of alphabetical order to prove the sort.
const COLLECTIONS: Collection[] = [
  collection("c1", "Zeta lib", "library"),
  collection("c2", "Alpha set", "generic"),
  collection("c3", "Beta lib", "library"),
];

vi.mock("@/features/research-organization/hooks/use-collections", () => ({
  useCollections: () => ({ data: COLLECTIONS }),
}));

function openPopover() {
  fireEvent.click(screen.getByRole("combobox"));
}

describe("CollectionMultiSelect", () => {
  it("trigger shows the placeholder when nothing is selected", () => {
    render(<CollectionMultiSelect value={[]} onChange={vi.fn()} />);
    expect(screen.getByText(/add a collection/i)).toBeInTheDocument();
  });

  it("trigger shows a count when collections are selected", () => {
    render(<CollectionMultiSelect value={["c1"]} onChange={vi.fn()} />);
    expect(screen.getByText(/1 collection selected/i)).toBeInTheDocument();
  });

  it("orders library collections before generic ones", () => {
    render(<CollectionMultiSelect value={[]} onChange={vi.fn()} />);
    openPopover();
    const options = screen.getAllByRole("option");
    const names = options.map((o) => within(o).getByText(/lib|set/).textContent);
    // Both libraries precede the generic "Alpha set" (library-first); within the
    // library group ties break alphabetically (Beta before Zeta).
    expect(names).toEqual(["Beta lib", "Zeta lib", "Alpha set"]);
    // The generic collection is last regardless of its alphabetically-first name.
    expect(names.indexOf("Alpha set")).toBe(names.length - 1);
  });

  it("selecting an option calls onChange with the toggled id", () => {
    const onChange = vi.fn();
    render(<CollectionMultiSelect value={[]} onChange={onChange} />);
    openPopover();
    const item = screen.getByText("Beta lib").closest("[data-slot='command-item']") as HTMLElement;
    expect(item).not.toBeNull();
    fireEvent.click(item);
    expect(onChange).toHaveBeenCalledWith(["c3"]);
  });

  it("renders a removable chip for a pre-selected value", () => {
    const onChange = vi.fn();
    render(<CollectionMultiSelect value={["c1"]} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /remove zeta lib/i }));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});
