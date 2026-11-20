import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RunPotencyFilter } from "./run-dr-results-filtering";
import { RunCurveClassFilterMenu, RunPotencyFilterControl } from "./run-dr-results-filters";

afterEach(cleanup);
const spec = { kind: "ec", level: 50, basis: "relative_percent", label: null } as const;

describe("named run table filters", () => {
  it("offers actual curve classes instead of generic text matching", () => {
    const change = vi.fn();
    render(<RunCurveClassFilterMenu selected={[]} onChange={change} hasUnclassified={false} />);
    fireEvent.keyDown(screen.getByRole("button", { name: "Filter by curve class" }), {
      key: "Enter",
    });
    fireEvent.click(screen.getByRole("menuitemcheckbox", { name: "Full" }));
    expect(change).toHaveBeenCalledWith(["full"]);
    expect(screen.getByRole("menuitemcheckbox", { name: "Active at all doses" })).toBeVisible();
  });
  it("applies a clearly labeled endpoint threshold and converts its form when units change", () => {
    const change = vi.fn();
    const { rerender } = render(
      <RunPotencyFilterControl intercepts={[spec]} unit="uM" value={null} onChange={change} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Filter by potency" }));
    fireEvent.change(screen.getByLabelText("Concentration (µM)"), { target: { value: "0.001" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filter" }));
    const applied: RunPotencyFilter = {
      spec,
      primary: true,
      operator: "lte",
      threshold: 0.001,
      unit: "uM",
    };
    expect(change).toHaveBeenCalledWith(applied);
    rerender(
      <RunPotencyFilterControl intercepts={[spec]} unit="nM" value={applied} onChange={change} />,
    );
    expect(screen.getByRole("button", { name: "Filter by potency" })).toHaveTextContent(
      "EC50 ≤ 1 nM",
    );
    fireEvent.click(screen.getByRole("button", { name: "Filter by potency" }));
    expect(screen.getByLabelText("Concentration (nM)")).toHaveValue(1);
  });
});
