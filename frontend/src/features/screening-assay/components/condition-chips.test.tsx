import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConditionChips } from "./condition-chips";

describe("ConditionChips", () => {
  it("renders an em-dash when there are no conditions", () => {
    render(<ConditionChips conditions={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders a custom empty fallback", () => {
    render(<ConditionChips conditions={{}} emptyFallback={<span>None</span>} />);
    expect(screen.getByText("None")).toBeInTheDocument();
  });

  it("renders one chip per condition as key + value", () => {
    render(<ConditionChips conditions={{ "Carbon Source": "glucose", ATP: "10 uM" }} />);
    expect(screen.getByText("Carbon Source:")).toBeInTheDocument();
    expect(screen.getByText("glucose")).toBeInTheDocument();
    expect(screen.getByText("ATP:")).toBeInTheDocument();
    expect(screen.getByText("10 uM")).toBeInTheDocument();
  });

  it("collapses overflow beyond `max` into a +N chip", () => {
    render(<ConditionChips conditions={{ a: "1", b: "2", c: "3", d: "4" }} max={2} />);
    expect(screen.getByText("a:")).toBeInTheDocument();
    expect(screen.getByText("b:")).toBeInTheDocument();
    expect(screen.queryByText("c:")).not.toBeInTheDocument();
    // Two hidden → "+2", with the hidden entries in the tooltip.
    const overflow = screen.getByText("+2");
    expect(overflow).toBeInTheDocument();
    expect(overflow).toHaveAttribute("title", "c: 3, d: 4");
  });
});
