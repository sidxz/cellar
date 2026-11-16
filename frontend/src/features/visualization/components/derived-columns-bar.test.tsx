import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DerivedEntry } from "../hooks/use-derived";
import type { DerivedSet, DerivedSpec } from "../lib/derived";
import type { Dataset } from "../types";

vi.mock("@/shared/components/chemistry", () => ({ StructureThumbnail: () => null }));
vi.mock("../lib/derived", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/derived")>();
  return { ...actual, coverage: vi.fn(actual.coverage) };
});

import { coverage } from "../lib/derived";
import { DerivedColumnsBar } from "./derived-columns-bar";

const ds: Dataset = {
  revision: "r",
  level: "compounds",
  row_count: 3,
  row_ids: ["m1", "m2", "m3"],
  columns: [],
  values: { molecule_id: ["m1", "m2", "m3"], structure: ["C", "CC", "CCC"] },
};

const rg1: DerivedSpec = {
  id: "rg1",
  kind: "rgroups",
  coreSmiles: "c1ccccc1[*:1]",
  name: "Core A",
};
const clusters: DerivedSpec = { id: "clusters", kind: "clusters", threshold: 0.4 };

const entry = (spec: DerivedSpec, over: Partial<DerivedEntry> = {}): DerivedEntry => ({
  spec,
  moleculeIds: ["m1", "m2", "m3"],
  status: "running",
  startedAt: Date.now(),
  attempt: 1,
  ...over,
});

const setFor = (spec: DerivedSpec, ids: string[], over: Partial<DerivedSet> = {}): DerivedSet => ({
  spec,
  columns: [],
  byMolecule: new Map(ids.map((id) => [id, {}])),
  summary: "R1 · 2 of 3 match",
  ...over,
});

const handlers = () => ({
  onCancel: vi.fn(),
  onRetry: vi.fn(),
  onRemove: vi.fn(),
  onRecompute: vi.fn(),
  onPlot: vi.fn(),
});

function renderBar(entries: DerivedEntry[], plotsFull = false) {
  const h = handlers();
  render(<DerivedColumnsBar entries={entries} ds={ds} plotsFull={plotsFull} {...h} />);
  return h;
}

describe("DerivedColumnsBar", () => {
  it("shows a running job's elapsed time and cancels it", () => {
    const h = renderBar([entry(rg1, { startedAt: Date.now() - 5_000 })]);
    expect(screen.getByText("R-groups · Core A")).toBeInTheDocument();
    expect(screen.getByText("Running · 0:05")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel R-groups · Core A" }));
    expect(h.onCancel).toHaveBeenCalledWith("rg1");
  });

  it("shows a failure with the server's message, Retry and remove", () => {
    const h = renderBar([
      entry(clusters, {
        status: "failed",
        error: "Cluster map capped at 50000 molecules; refine the filter.",
      }),
    ]);
    expect(screen.getByText("Clusters · threshold 0.4")).toBeInTheDocument();
    expect(
      screen.getByText("failed: Cluster map capped at 50000 molecules; refine the filter."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(h.onRetry).toHaveBeenCalledWith("clusters");
    fireEvent.click(screen.getByRole("button", { name: "Remove Clusters · threshold 0.4" }));
    expect(h.onRemove).toHaveBeenCalledWith("clusters");
  });

  it("offers Run again after a cancel", () => {
    const h = renderBar([entry(rg1, { status: "cancelled" })]);
    expect(screen.getByText("Cancelled")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run again" }));
    expect(h.onRetry).toHaveBeenCalledWith("rg1");
  });

  it("shows a ready set's summary, its warning, and how many compounds it covers", () => {
    const set = setFor(rg1, ["m1", "m2"], {
      warning: "Only 1 of 3 compounds match this core",
    });
    const h = renderBar([entry(rg1, { status: "ready", set })]);
    expect(screen.getByText("R1 · 2 of 3 match")).toBeInTheDocument();
    expect(screen.getByText("Only 1 of 3 compounds match this core")).toHaveClass("text-warning");
    expect(screen.getByText("Computed for 2 of 3 compounds")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Recompute" }));
    expect(h.onRecompute).toHaveBeenCalledWith("rg1");
    fireEvent.click(screen.getByRole("button", { name: "Matrix" }));
    expect(h.onPlot).toHaveBeenCalledWith("rg1");
  });

  it("says nothing of coverage when the set covers every compound", () => {
    renderBar([entry(rg1, { status: "ready", set: setFor(rg1, ["m1", "m2", "m3"]) })]);
    expect(screen.queryByText(/Computed for/)).not.toBeInTheDocument();
  });

  it("adds the cluster map, unless four plots are open", () => {
    const set = setFor(clusters, ["m1", "m2", "m3"], { summary: "2 clusters" });
    const h = renderBar([entry(clusters, { status: "ready", set })]);
    fireEvent.click(screen.getByRole("button", { name: "Show map" }));
    expect(h.onPlot).toHaveBeenCalledWith("clusters");
  });

  it("announces each job's status as it changes, never the ticking clock", () => {
    const h = handlers();
    const running = entry(rg1, { startedAt: Date.now() - 5_000 });
    const { rerender } = render(
      <DerivedColumnsBar entries={[running]} ds={ds} plotsFull={false} {...h} />,
    );
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("R-groups · Core A running");
    expect(status).not.toHaveTextContent("0:05");
    const failed = { ...running, status: "failed" as const, error: "No compound matches." };
    rerender(<DerivedColumnsBar entries={[failed]} ds={ds} plotsFull={false} {...h} />);
    expect(status).toHaveTextContent("R-groups · Core A failed: No compound matches.");
    const ready = { ...running, status: "ready" as const, set: setFor(rg1, ["m1", "m2"]) };
    rerender(<DerivedColumnsBar entries={[ready]} ds={ds} plotsFull={false} {...h} />);
    expect(status).toHaveTextContent("R-groups · Core A ready: R1 · 2 of 3 match");
  });

  it("counts a ready set's coverage once, not on every tick of a running job's clock", () => {
    vi.useFakeTimers();
    try {
      renderBar([entry(rg1, { status: "ready", set: setFor(rg1, ["m1", "m2"]) }), entry(clusters)]);
      const before = vi.mocked(coverage).mock.calls.length;
      act(() => vi.advanceTimersByTime(3_000));
      expect(screen.getByText("Running · 0:03")).toBeInTheDocument();
      expect(vi.mocked(coverage).mock.calls.length).toBe(before);
    } finally {
      vi.useRealTimers();
    }
  });

  it("disables the plot button with four plots open", () => {
    const set = setFor(clusters, ["m1", "m2", "m3"], { summary: "2 clusters" });
    renderBar([entry(clusters, { status: "ready", set })], true);
    expect(screen.getByRole("button", { name: "Show map" })).toBeDisabled();
  });
});
