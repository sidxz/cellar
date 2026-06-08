import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CollectionCoverage } from "../types";
import { CoverageChip } from "./coverage-chip";

// `CollectionTypeIcon` is a bare lucide svg with no data deps, so these are
// pure presentational assertions — no hook mocking or QueryClientProvider.

const coverage = (over: Partial<CollectionCoverage> = {}): CollectionCoverage => ({
  id: "c1",
  name: "Library SACCZ",
  type: "library",
  covered: 1840,
  total: 2000,
  fraction: 0.92,
  ...over,
});

describe("CoverageChip", () => {
  it("renders covered/total and rounded percent", () => {
    render(<CoverageChip coverage={coverage()} />);
    expect(screen.getByText("1,840/2,000 · 92%")).toBeInTheDocument();
  });

  it("shows a 'N remaining' button when a gap remains and onViewGap is given", () => {
    const onViewGap = vi.fn();
    render(<CoverageChip coverage={coverage()} onViewGap={onViewGap} />);
    const btn = screen.getByRole("button", { name: "160 remaining" });
    fireEvent.click(btn);
    expect(onViewGap).toHaveBeenCalledTimes(1);
  });

  it("hides the remaining button when the collection is fully covered", () => {
    render(
      <CoverageChip coverage={coverage({ covered: 2000, fraction: 1 })} onViewGap={vi.fn()} />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("2,000/2,000 · 100%")).toBeInTheDocument();
  });

  it("renders an em-dash (not NaN%) for an empty collection", () => {
    render(<CoverageChip coverage={coverage({ covered: 0, total: 0, fraction: null })} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });

  it("renders an em-dash when fraction is null even if total > 0", () => {
    render(<CoverageChip coverage={coverage({ fraction: null })} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
