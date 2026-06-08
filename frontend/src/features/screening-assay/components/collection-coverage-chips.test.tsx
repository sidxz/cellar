import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { CollectionCoverage } from "../types";
import { CollectionCoverageChips } from "./collection-coverage-chips";

// `CollectionTypeIcon` renders a bare lucide svg with no data deps, so these are
// pure presentational assertions — no hook mocking or QueryClientProvider needed.

const coverage = (over: Partial<CollectionCoverage> = {}): CollectionCoverage => ({
  id: "c1",
  name: "Kinase Set",
  type: "library",
  covered: 1840,
  total: 2000,
  fraction: 0.92,
  ...over,
});

describe("CollectionCoverageChips", () => {
  it("renders the rounded percent for a coverage item", () => {
    render(<CollectionCoverageChips collections={[coverage()]} />);
    expect(screen.getByText("92%")).toBeInTheDocument();
  });

  it("collapses overflow past `max` into a `+N` badge", () => {
    const items = [
      coverage({ id: "c1", name: "Alpha", fraction: 0.5 }),
      coverage({ id: "c2", name: "Beta", fraction: 0.25 }),
      coverage({ id: "c3", name: "Gamma", fraction: 0.1 }),
    ];
    render(<CollectionCoverageChips collections={items} max={1} />);
    // Only the first chip's percent shows; the rest collapse to a `+2` badge.
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.queryByText("25%")).not.toBeInTheDocument();
    expect(screen.queryByText("10%")).not.toBeInTheDocument();
    expect(screen.getByText("+2")).toBeInTheDocument();
  });

  it("renders an em-dash for an empty collections array", () => {
    render(<CollectionCoverageChips collections={[]} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders an em-dash when collections is undefined", () => {
    render(<CollectionCoverageChips collections={undefined} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders an em-dash (not NaN%) when a chip's fraction is null", () => {
    render(<CollectionCoverageChips collections={[coverage({ fraction: null })]} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });
});
