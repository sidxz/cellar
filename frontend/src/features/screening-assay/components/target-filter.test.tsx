import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { TargetFilter } from "./target-filter";

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
      { id: "t1", name: "InhA", target_type: "protein" },
      { id: "t2", name: "DnaE1", target_type: "protein" },
    ],
  }),
}));

describe("TargetFilter", () => {
  it("toggles a target and reports it via onChange", () => {
    const onChange = vi.fn();
    render(<TargetFilter value={{ targetIds: [], targetLogic: "any" }} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button")); // open popover
    fireEvent.click(screen.getByText("InhA"));
    expect(onChange).toHaveBeenCalledWith({ targetIds: ["t1"], targetLogic: "any" });
  });
});
