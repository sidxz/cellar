import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Dataset, DatasetColumn } from "../types";
import { CurvesDialog, curvesTarget } from "./curves-dialog";

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
const R1 = "11111111-1111-4111-8111-111111111111";
const R2 = "22222222-2222-4222-8222-222222222222";
const R3 = "33333333-3333-4333-8333-333333333333";
const U1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const U2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const P1 = "99999999-9999-4999-8999-999999999999";
const M1 = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const B1 = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const RD = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
const OTHER_RD = "ffffffff-ffff-4fff-8fff-ffffffffffff";

const state = vi.hoisted(() => ({ curves: [] as Record<string, unknown>[] }));

vi.mock("@/shared/lib/plotly", () => ({ Plot: () => null }));
vi.mock("@structflo/components/dose-response", () => ({
  DoseResponseChartView: ({ curves }: { curves: { label?: string }[] }) => (
    <ul aria-label="Chart">
      {curves.map((c) => (
        <li key={c.label}>{c.label}</li>
      ))}
    </ul>
  ),
}));
vi.mock("@/features/screening-assay/hooks/use-compound-curves", () => ({
  useCompoundCurves: () => ({ data: state.curves, isLoading: false }),
}));
vi.mock("@/features/screening-assay/hooks/use-runs", () => ({
  useRunsByProtocol: () => ({
    data: [
      { id: R1, run_date: "2026-11-12", operator: U1 },
      { id: R2, run_date: "2026-11-13", operator: U2 },
      { id: R3, run_date: "2026-11-14", operator: U1 },
    ],
  }),
}));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useMemberNames: () => (id: string) => ({ [U1]: "A. Chen", [U2]: "B. Diaz" })[id] ?? "",
}));

const curve = (id: string, run_id: string, fitted_value: number, readout = RD) => ({
  id,
  molecule_id: M1,
  run_id,
  batch_id: B1,
  batch_number: "001",
  readout_definition_id: readout,
  curve_type: "ic50",
  fitted_value,
  fitted_unit: "µM",
  top: 100,
  bottom: 0,
  hill_slope: 1,
  r_squared: 0.99,
  curve_class: "active",
});

const target = {
  protocolId: P1,
  readoutDefinitionId: RD,
  moleculeId: M1,
  compound: "CEL-1",
  readout: "Enzyme · IC50",
  batchId: null,
};

describe("CurvesDialog", () => {
  it("shows the compound's curves in the chosen runs, runs named by date and operator", () => {
    state.curves = [
      curve("c1", R1, 0.25),
      curve("c2", R2, 0.5),
      curve("c3", R3, 1),
      curve("c4", R1, 9, OTHER_RD),
    ];
    render(<CurvesDialog {...target} runIds={[R1, R2]} open onOpenChange={() => {}} />);
    const dialog = screen.getByRole("dialog", { name: "CEL-1 · Enzyme · IC50" });
    expect(
      within(screen.getByRole("list", { name: "Chart" })).getAllByRole("listitem"),
    ).toHaveLength(2);
    expect(within(dialog).getAllByText("2026-11-12 · A. Chen").length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText("2026-11-13 · B. Diaz").length).toBeGreaterThan(0);
    expect(within(dialog).queryByText(/2026-11-14/)).not.toBeInTheDocument();
    expect(within(dialog).getByText("0.25 µM")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(UUID);
  });

  it("keeps to the row's batch", () => {
    state.curves = [curve("c1", R1, 0.25), { ...curve("c2", R2, 0.5), batch_id: "other" }];
    render(
      <CurvesDialog {...target} batchId={B1} runIds={[R1, R2]} open onOpenChange={() => {}} />,
    );
    expect(
      within(screen.getByRole("list", { name: "Chart" })).getAllByRole("listitem"),
    ).toHaveLength(1);
  });

  it("says when the chosen runs have no curves for the compound", () => {
    state.curves = [curve("c3", R3, 1)];
    render(<CurvesDialog {...target} runIds={[R1]} open onOpenChange={() => {}} />);
    expect(screen.getByText("No curves for CEL-1 in the chosen runs.")).toBeInTheDocument();
  });
});

describe("curvesTarget", () => {
  const prov = { protocol_id: P1, readout_definition_id: RD, layer: null };
  const col = (key: string, extra: Partial<DatasetColumn> = {}): DatasetColumn => ({
    key,
    label: key === "dr:e" ? "Enzyme · IC50" : key,
    kind: "category",
    provenance: {},
    ...extra,
  });

  it("opens a Runs row on its own run and batch", () => {
    const ds: Dataset = {
      revision: "r",
      level: "runs",
      row_count: 1,
      row_ids: [`${R2}:${M1}:${B1}`],
      columns: [
        col("compound"),
        col("molecule_id", { hidden: true }),
        col("batch_id", { hidden: true }),
        col("dr:e", { kind: "number", provenance: { ...prov, aggregation: "fit" } }),
      ],
      values: { compound: ["CEL-1"], molecule_id: [M1], batch_id: [B1], "dr:e": [0.5] },
    };
    expect(curvesTarget(ds, "dr:e", 0, [R1, R2])).toEqual({
      ...target,
      runIds: [R2],
      batchId: B1,
    });
  });

  it("opens a Compounds row over the runs that count", () => {
    const ds: Dataset = {
      revision: "r",
      level: "compounds",
      row_count: 1,
      row_ids: [M1],
      columns: [
        col("compound"),
        col("molecule_id", { hidden: true }),
        col("dr:e", { kind: "number", provenance: { ...prov, aggregation: "geomean" } }),
      ],
      values: { compound: ["CEL-1"], molecule_id: [M1], "dr:e": [0.5] },
    };
    expect(curvesTarget(ds, "dr:e", 0, [R1, R2])).toEqual({ ...target, runIds: [R1, R2] });
  });
});
