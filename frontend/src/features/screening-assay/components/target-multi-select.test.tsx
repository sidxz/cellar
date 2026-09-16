import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { TargetMultiSelect } from "./target-multi-select";

// Radix Popover/Command items need pointer-event stubs in jsdom.
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

vi.mock("../hooks/use-targets", () => ({
  useTargets: () => ({
    data: [
      { id: "t-1", name: "EGFR", target_type: "single_protein" },
      { id: "t-2", name: "BRAF", target_type: "single_protein" },
    ],
  }),
}));

// The trigger sets role="combobox" (mirrors SearchableSelect), so it is
// queried as a combobox — not a button.
function openPopover() {
  fireEvent.click(screen.getByRole("combobox"));
}

describe("TargetMultiSelect", () => {
  it("trigger shows the placeholder when nothing is selected", () => {
    render(<TargetMultiSelect value={[]} onChange={vi.fn()} />);
    // A combobox-role element takes its accessible name from a label, not its
    // text, so assert the visible trigger text directly.
    expect(screen.getByText(/select targets/i)).toBeInTheDocument();
  });

  it("trigger shows a count when targets are selected", () => {
    render(<TargetMultiSelect value={["t-1"]} onChange={vi.fn()} />);
    expect(screen.getByText(/1 target selected/i)).toBeInTheDocument();
  });

  it("opening the popover lists the available targets and a search box", () => {
    render(<TargetMultiSelect value={[]} onChange={vi.fn()} />);
    openPopover();
    expect(screen.getByPlaceholderText(/search targets/i)).toBeInTheDocument();
    expect(screen.getByText("EGFR")).toBeInTheDocument();
    expect(screen.getByText("BRAF")).toBeInTheDocument();
    // The inline "Manage in Prot-Cellar" affordance is offered too.
    expect(screen.getByText(/manage in prot-cellar/i)).toBeInTheDocument();
  });

  it("selecting a target adds its id via onChange", () => {
    const onChange = vi.fn();
    render(<TargetMultiSelect value={[]} onChange={onChange} />);
    openPopover();
    const item = screen.getByText("EGFR").closest("[data-slot='command-item']") as HTMLElement;
    expect(item).not.toBeNull();
    fireEvent.click(item);
    expect(onChange).toHaveBeenCalledWith(["t-1"]);
  });

  it("selecting an already-selected target removes it (toggle)", () => {
    const onChange = vi.fn();
    render(<TargetMultiSelect value={["t-1"]} onChange={onChange} />);
    openPopover();
    // "EGFR" appears twice when selected (the popover option + the chip), so
    // scope the click to the command-item, not the chip badge.
    const item = screen
      .getAllByText("EGFR")
      .map((el) => el.closest("[data-slot='command-item']"))
      .find((el): el is HTMLElement => el !== null);
    expect(item).toBeTruthy();
    fireEvent.click(item as HTMLElement);
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("removing a selected chip calls onChange without that id", () => {
    const onChange = vi.fn();
    render(<TargetMultiSelect value={["t-1", "t-2"]} onChange={onChange} />);
    // Each selected target renders a removable chip with an aria-labelled button.
    fireEvent.click(screen.getByRole("button", { name: /remove egfr/i }));
    expect(onChange).toHaveBeenCalledWith(["t-2"]);
  });

  it("'Manage in Prot-Cellar' opens the catalog in a new tab", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    render(<TargetMultiSelect value={[]} onChange={vi.fn()} />);
    openPopover();
    const item = screen
      .getByText(/manage in prot-cellar/i)
      .closest("[data-slot='command-item']") as HTMLElement;
    fireEvent.click(item);
    expect(open).toHaveBeenCalledWith(
      "http://localhost:3001/targets",
      "_blank",
      "noopener,noreferrer",
    );
    open.mockRestore();
  });
});
