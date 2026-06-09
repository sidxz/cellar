import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CoverageBar } from "./coverage-bar";

const base = { id: "c1", name: "Kinase Set", type: "library" as const };

describe("CoverageBar", () => {
  it("shows covered/total and percent", () => {
    render(<CoverageBar coverage={{ ...base, covered: 1840, total: 2000, fraction: 0.92 }} />);
    expect(screen.getByText(/1,840\s*\/\s*2,000/)).toBeInTheDocument();
    expect(screen.getByText(/92%/)).toBeInTheDocument();
  });
  it("renders an em-dash for an empty collection", () => {
    render(<CoverageBar coverage={{ ...base, covered: 0, total: 0, fraction: null }} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
  it("exposes a remaining affordance when onViewGap is provided", () => {
    render(
      <CoverageBar
        coverage={{ ...base, covered: 1840, total: 2000, fraction: 0.92 }}
        onViewGap={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: /160 remaining/i })).toBeInTheDocument();
  });
});
