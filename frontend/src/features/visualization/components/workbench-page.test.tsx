import { ApiError } from "@/shared/lib/api/custom-instance";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Dataset, DatasetColumn } from "../types";

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const R1 = "11111111-1111-4111-8111-111111111111";
const R2 = "22222222-2222-4222-8222-222222222222";
const R3 = "33333333-3333-4333-8333-333333333333";
const U1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const P1 = "99999999-9999-4999-8999-999999999999";
const names: Record<string, string> = { [U1]: "A. Chen" };
const runs = [
  { id: R1, run_date: "2026-11-12", status: "approved", conditions: { NADP: "+" } },
  { id: R2, run_date: "2026-11-05", status: "completed", conditions: null },
  { id: R3, run_date: "2026-10-29", status: "draft", conditions: null },
].map((r) => ({ ...r, created_at: "1", operator: U1, plate_count: 1, protocol_id: P1 }));

const state = vi.hoisted(() => ({
  query: {} as Record<string, unknown>,
  counts: undefined as Record<string, number> | undefined,
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useMemberNames: () => (id: string) => names[id] ?? "",
}));
vi.mock("@/features/screening-assay/hooks/use-runs", () => ({
  useRunsByProtocol: () => ({ data: runs, isLoading: false }),
  useRun: (id: string) => ({ data: runs.find((r) => r.id === id) }),
}));
vi.mock("@/features/screening-assay/hooks/use-protocols", () => ({
  useProtocol: () => ({ data: { id: P1, name: "NadD HTS" } }),
}));
vi.mock("../hooks/use-dataset", () => ({ useDataset: () => state.query }));
vi.mock("../hooks/use-run-row-counts", () => ({
  useRunRowCounts: (id: string | null) => ({
    data: id && state.counts ? { counts: state.counts } : undefined,
  }),
}));

import { WorkbenchPage } from "./workbench-page";

const col = (key: string, kind: DatasetColumn["kind"], hidden = false): DatasetColumn => ({
  key,
  label: key,
  kind,
  provenance: {},
  hidden,
});

function dataset(numeric = true): Dataset {
  return {
    revision: "rev",
    level: "wells",
    row_count: 3,
    row_ids: ["w1", "w2", "w3"],
    columns: [
      col("compound", "category"),
      col("molecule_id", "text", true),
      col("plate", "category"),
      col("well_type", "category"),
      col("well_order", "number"),
      col("operator", "user"),
      col("rd:s:raw", numeric ? "number" : "category"),
    ],
    values: {
      compound: ["CEL-1", "CEL-2", null],
      molecule_id: ["m1", "m2", null],
      plate: ["1", "1", "1"],
      well_type: ["sample", "sample", "negative_control"],
      well_order: [1, 2, 3],
      operator: [U1, U1, U1],
      "rd:s:raw": numeric ? [1, 2, 3] : ["a", "b", "c"],
    },
  };
}

const ready = (ds: Dataset) => ({ data: ds, isPending: false, isError: false, refetch: vi.fn() });

beforeEach(() => {
  state.counts = undefined;
  state.query = ready(dataset());
});

describe("WorkbenchPage", () => {
  it("shows the server's 422 message with a Retry that refetches", () => {
    const refetch = vi.fn();
    const message = "This selection has 410 columns; the limit is 400. Choose fewer runs.";
    state.query = {
      isPending: false,
      isError: true,
      error: new ApiError(`API error: 422 — ${message}`, 422, { message }),
      refetch,
    };
    render(<WorkbenchPage source={{ kind: "run", runId: R1 }} />);
    expect(screen.getByText(message)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetch).toHaveBeenCalled();
  });

  it("over the row cap, shows the count and reopens the run picker", () => {
    state.counts = { [R1]: 150_000, [R2]: 100_000, [R3]: 0 };
    render(<WorkbenchPage source={{ kind: "protocol", protocolId: P1 }} />);
    expect(screen.getByText(/250,000 wells/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Choose fewer runs" }));
    expect(screen.getByRole("dialog", { name: "Choose runs to visualize" })).toBeInTheDocument();
  });

  it("says so when the runs have no readout data", () => {
    state.query = ready({ ...dataset(), row_count: 0, row_ids: [], values: {} });
    render(<WorkbenchPage source={{ kind: "run", runId: R1 }} />);
    expect(screen.getByText("These runs have no readout data yet")).toBeInTheDocument();
  });

  it("flags a dataset with no numeric fields", () => {
    state.query = ready(dataset(false));
    render(<WorkbenchPage source={{ kind: "run", runId: R1 }} />);
    expect(screen.getByText(/no numeric fields to plot/i)).toBeInTheDocument();
  });

  it("heads the workbench with the source, grain, counts and history buttons", () => {
    render(<WorkbenchPage source={{ kind: "protocol", protocolId: P1, runIds: [R1, R2] }} />);
    expect(screen.getByRole("link", { name: /NadD HTS/ })).toHaveAttribute(
      "href",
      `/assays/protocols/${P1}`,
    );
    expect(screen.getByText("Each row: one well")).toBeInTheDocument();
    expect(screen.getByText("3 / 3 wells · 2 compounds")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Redo" })).toBeDisabled();
  });

  it("lists the source runs as date · operator in the popover, with no UUIDs", () => {
    render(<WorkbenchPage source={{ kind: "protocol", protocolId: P1, runIds: [R1, R2] }} />);
    fireEvent.click(screen.getByRole("button", { name: /2 of 3 runs/ }));
    expect(screen.getByText("2026-11-12 · A. Chen")).toBeInTheDocument();
    expect(screen.getByText("2026-11-05 · A. Chen")).toBeInTheDocument();
    expect(screen.queryByText(/2026-10-29/)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(UUID);
  });
});
