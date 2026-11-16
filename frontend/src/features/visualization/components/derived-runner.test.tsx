import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DerivedEntry } from "../hooks/use-derived";
import type { Dataset } from "../types";

const state = vi.hoisted(() => ({
  decomposition: {} as Record<string, unknown>,
  assignments: {} as Record<string, unknown>,
  umap: {} as Record<string, unknown>,
  moleculeIds: [] as unknown[],
  nonces: [] as unknown[],
}));

vi.mock("@/features/sar-analysis/hooks/use-decomposition-run", () => ({
  useDecompositionRun: (p: { moleculeIds: string[]; nonce: string }) => {
    state.moleculeIds.push(p.moleculeIds);
    state.nonces.push(p.nonce);
    return state.decomposition;
  },
}));
vi.mock("@/features/sar-analysis/hooks/use-umap-cluster", () => ({
  useUmapCluster: (p: { moleculeIds: string[]; nonce: string }) => {
    state.moleculeIds.push(p.moleculeIds);
    state.nonces.push(p.nonce);
    return state.umap;
  },
}));
vi.mock("@/features/sar-analysis/hooks/use-scaffold-tree", () => ({
  useScaffoldTree: (p: { nonce: string }) => {
    state.nonces.push(p.nonce);
    return { tree: null, error: null };
  },
}));
vi.mock("../hooks/use-rgroup-assignments", () => ({
  useRGroupAssignments: (runId: string | null) =>
    runId ? state.assignments : { data: undefined, error: null },
}));

import { DerivedRunner } from "./derived-runner";

const ds: Dataset = {
  revision: "r",
  level: "compounds",
  row_count: 2,
  row_ids: ["m1", "m2"],
  columns: [],
  values: { molecule_id: ["m1", "m2"], structure: ["c1ccccc1Cl", "c1ccccc1"] },
};

const running = (spec: DerivedEntry["spec"]): DerivedEntry => ({
  spec,
  moleculeIds: ["m1", "m2"],
  status: "running",
  startedAt: 0,
  attempt: 1,
});
const rg1 = running({ id: "rg1", kind: "rgroups", coreSmiles: "c1ccccc1[*:1]", name: "Core A" });
const clusters = running({ id: "clusters", kind: "clusters", threshold: 0.4 });

const decomposition = (over: Record<string, unknown> = {}) => ({
  runId: "run-1",
  status: "ready",
  counts: { matched: 2, unmatched: 0, total: 2 },
  error: null,
  isCancelled: false,
  cancel: vi.fn(),
  ...over,
});

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  state.moleculeIds = [];
  state.nonces = [];
  state.decomposition = decomposition();
  state.assignments = {
    data: {
      core_smiles: "c1ccccc1[*:1]",
      labels: ["R1"],
      assignments: { m1: { R1: "Cl[*:1]" }, m2: { R1: "[H][*:1]" } },
    },
    error: null,
  };
  state.umap = { result: null, error: null, cancel: vi.fn() };
});

describe("DerivedRunner", () => {
  it("resolves R-groups from the run's assignments", () => {
    const dispatch = vi.fn();
    render(<DerivedRunner entry={rg1} ds={ds} readySets={[]} dispatch={dispatch} />, { wrapper });
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: "resolve", id: "rg1" }));
    const { set } = dispatch.mock.calls[0][0];
    expect(set.columns.map((c: { key: string }) => c.key)).toContain("chem:rg1:R1");
    expect(set.byMolecule.get("m1")["chem:rg1:R1"]).toBe("Cl");
  });

  it("builds the columns over the compounds its job ran over, not ones added since", () => {
    const grown: Dataset = {
      ...ds,
      row_count: 3,
      row_ids: ["m1", "m2", "m3"],
      values: { molecule_id: ["m1", "m2", "m3"], structure: ["c1ccccc1Cl", "c1ccccc1", "CCO"] },
    };
    const dispatch = vi.fn();
    render(<DerivedRunner entry={rg1} ds={grown} readySets={[]} dispatch={dispatch} />, {
      wrapper,
    });
    const { set } = dispatch.mock.calls[0][0];
    expect([...set.byMolecule.keys()]).toEqual(["m1", "m2"]);
  });

  it("fails when no compound matches the core, without reading assignments", () => {
    state.decomposition = decomposition({ counts: { matched: 0, unmatched: 2, total: 2 } });
    state.assignments = { data: undefined, error: new Error("must not be read") };
    const dispatch = vi.fn();
    render(<DerivedRunner entry={rg1} ds={ds} readySets={[]} dispatch={dispatch} />, { wrapper });
    expect(dispatch).toHaveBeenCalledWith({
      type: "fail",
      id: "rg1",
      message: "No compound in this dataset matches the core.",
    });
  });

  it("fails with the server's own sentence", () => {
    state.umap = {
      result: null,
      error: "API error: 400 — Cluster map capped at 50000 molecules; refine the filter.",
      cancel: vi.fn(),
    };
    const dispatch = vi.fn();
    render(<DerivedRunner entry={clusters} ds={ds} readySets={[]} dispatch={dispatch} />, {
      wrapper,
    });
    expect(dispatch).toHaveBeenCalledWith({
      type: "fail",
      id: "clusters",
      message: "Cluster map capped at 50000 molecules; refine the filter.",
    });
  });

  it("hands the job the entry's own compound array on every render", () => {
    state.decomposition = decomposition({ status: "running", runId: null });
    const dispatch = vi.fn();
    const { rerender } = render(
      <DerivedRunner entry={rg1} ds={ds} readySets={[]} dispatch={dispatch} />,
      { wrapper },
    );
    rerender(
      <DerivedRunner entry={{ ...rg1 }} ds={{ ...ds }} readySets={[]} dispatch={dispatch} />,
    );
    expect(state.moleculeIds.length).toBeGreaterThan(1);
    for (const ids of state.moleculeIds) expect(ids).toBe(rg1.moleculeIds);
    expect(dispatch).not.toHaveBeenCalled();
  });

  it("starts each attempt of a set as a job of its own", () => {
    state.decomposition = decomposition({ status: "running", runId: null });
    const series = running({
      id: "series",
      kind: "series",
      members: [{ name: "A", scaffold: "S" }],
    });
    for (const entry of [rg1, { ...rg1, attempt: 2 }, { ...clusters, attempt: 3 }, series]) {
      render(<DerivedRunner entry={entry} ds={ds} readySets={[]} dispatch={vi.fn()} />, {
        wrapper,
      }).unmount();
    }
    expect(new Set(state.nonces)).toEqual(new Set(["rg1:1", "rg1:2", "clusters:3", "series:1"]));
  });

  it("cancels the job when it stops before an answer", () => {
    const cancel = vi.fn();
    state.decomposition = decomposition({ status: "running", cancel });
    const { unmount } = render(
      <DerivedRunner entry={rg1} ds={ds} readySets={[]} dispatch={vi.fn()} />,
      { wrapper },
    );
    unmount();
    expect(cancel).toHaveBeenCalled();
  });

  it("does not cancel a job that answered", () => {
    const cancel = vi.fn();
    state.decomposition = decomposition({ cancel });
    const { unmount } = render(
      <DerivedRunner entry={rg1} ds={ds} readySets={[]} dispatch={vi.fn()} />,
      { wrapper },
    );
    unmount();
    expect(cancel).not.toHaveBeenCalled();
  });

  it("waits for the data before building the columns", () => {
    const dispatch = vi.fn();
    const { rerender } = render(
      <DerivedRunner entry={rg1} ds={undefined} readySets={[]} dispatch={dispatch} />,
      { wrapper },
    );
    expect(dispatch).not.toHaveBeenCalled();
    rerender(<DerivedRunner entry={rg1} ds={ds} readySets={[]} dispatch={dispatch} />);
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: "resolve" }));
  });

  it("fails a job with no compound to run over", () => {
    const dispatch = vi.fn();
    render(
      <DerivedRunner
        entry={{ ...clusters, moleculeIds: [] }}
        ds={ds}
        readySets={[]}
        dispatch={dispatch}
      />,
      { wrapper },
    );
    expect(dispatch).toHaveBeenCalledWith({
      type: "fail",
      id: "clusters",
      message: "No compound in this dataset has a structure.",
    });
  });
});
