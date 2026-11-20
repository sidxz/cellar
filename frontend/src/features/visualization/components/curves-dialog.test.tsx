import type { DoseResponseCurve } from "@/features/screening-assay/types";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { compoundCurve } from "../lib/traces/test-fixtures";
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

const state = vi.hoisted(() => ({ curves: [] as DoseResponseCurve[] }));

vi.mock("@/shared/lib/plotly", () => ({ Plot: () => null }));
vi.mock("@structflo/components/dose-response", () => ({
  DoseResponseChartView: ({
    curves,
    yRange,
  }: {
    curves: { label?: string; intercept_values?: { qualifier?: string | null }[] }[];
    yRange?: [number, number];
  }) => (
    <ul aria-label="Chart" data-y-range={JSON.stringify(yRange ?? null)}>
      {curves.map((c) => (
        <li key={c.label} data-qualifiers={c.intercept_values?.map((iv) => iv.qualifier).join()}>
          {c.label}
        </li>
      ))}
    </ul>
  ),
}));
// The real hook, answered at the HTTP edge with the endpoint's payload.
vi.mock("@/shared/lib/api/custom-instance", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/shared/lib/api/custom-instance")>()),
  customInstance: vi.fn(async () => state.curves),
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

const curve = (
  id: string,
  run_id: string,
  fitted_value: number,
  { readout = RD, batch_id = B1, batch_number = "CEL-000001-01" as string | null } = {},
) =>
  compoundCurve({
    id,
    run_id,
    fitted_value,
    molecule_id: M1,
    protocol_id: P1,
    readout_definition_id: readout,
    batch_id,
    batch_number,
  });

/** Opens the dialog and waits for the curves to load. */
async function openDialog(props: { runIds: string[]; batchId?: string | null }) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CurvesDialog {...target} {...props} open onOpenChange={() => {}} />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.queryByText("Loading curves…")).not.toBeInTheDocument());
}

const target = {
  protocolId: P1,
  readoutDefinitionId: RD,
  moleculeId: M1,
  compound: "CEL-1",
  readout: "Enzyme · IC50",
  batchId: null,
};

describe("CurvesDialog", () => {
  it("reads the endpoint's intercepts and layer: an n.d. curve is not a number, % frames 0-100", async () => {
    // What GET .../compounds/{molecule}/dose-response sends (tests/api/test_compound_dose_response):
    // the layer the curve fits, and its intercepts with their stored qualifiers.
    const spec = { kind: "ic", level: 50, basis: "relative_percent", label: null };
    state.curves = [
      {
        ...curve("c1", R1, 0.25),
        curve_class: "partial",
        fitted_layer: "percent_inhibition",
        raw_data: [
          { concentration: 0.01, response: 40 },
          { concentration: 10, response: 55 },
        ],
        intercept_values: [
          { spec, value: null, at_bound: false, qualifier: "nd" },
          { spec: { ...spec, level: 90 }, value: 10, at_bound: true, qualifier: ">" },
        ],
      },
    ];
    await openDialog({ runIds: [R1] });
    expect(vi.mocked(customInstance)).toHaveBeenCalledWith(
      expect.objectContaining({ url: `/api/v1/protocols/${P1}/compounds/${M1}/dose-response` }),
    );
    expect(screen.getByLabelText("Chart").getAttribute("data-y-range")).toBe("[-10,110]");
    expect(screen.getByRole("listitem").getAttribute("data-qualifiers")).toBe("nd,>");
    // The midpoint (0.25) is not the EC50: the table reads it as not determined.
    expect(screen.getByRole("cell", { name: "ND" })).toBeInTheDocument();
    expect(screen.queryByRole("cell", { name: "0.25 uM" })).not.toBeInTheDocument();
  });

  it("shows the compound's curves in the chosen runs, runs named by date and operator", async () => {
    state.curves = [
      curve("c1", R1, 0.25),
      curve("c2", R2, 0.5),
      curve("c3", R3, 1),
      curve("c4", R1, 9, { readout: OTHER_RD }),
    ];
    await openDialog({ runIds: [R1, R2] });
    const dialog = screen.getByRole("dialog", { name: "CEL-1 · Enzyme · IC50" });
    expect(
      within(screen.getByRole("list", { name: "Chart" })).getAllByRole("listitem"),
    ).toHaveLength(2);
    expect(within(dialog).getAllByText("2026-11-12 · A. Chen").length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText("2026-11-13 · B. Diaz").length).toBeGreaterThan(0);
    expect(within(dialog).queryByText(/2026-11-14/)).not.toBeInTheDocument();
    expect(within(dialog).getByText("0.25 uM")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(UUID);
  });

  it("keeps to the row's batch", async () => {
    state.curves = [curve("c1", R1, 0.25), curve("c2", R2, 0.5, { batch_id: "other" })];
    await openDialog({ batchId: B1, runIds: [R1, R2] });
    expect(
      within(screen.getByRole("list", { name: "Chart" })).getAllByRole("listitem"),
    ).toHaveLength(1);
  });

  it("names each curve's batch when the run tested several", async () => {
    state.curves = [
      curve("c1", R1, 0.25),
      curve("c2", R1, 0.5, { batch_id: "b2", batch_number: "CEL-000001-02" }),
      curve("c3", R2, 1, { batch_id: "b3", batch_number: null }),
    ];
    await openDialog({ runIds: [R1, R2] });
    expect(
      within(screen.getByRole("list", { name: "Chart" }))
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual([
      "2026-11-12 · A. Chen · CEL-000001-01",
      "2026-11-12 · A. Chen · CEL-000001-02",
      "2026-11-13 · B. Diaz",
    ]);
    expect(screen.getByRole("cell", { name: "CEL-000001-02" })).toBeInTheDocument();
  });

  it("reads an inactive curve's value as above its top dose", async () => {
    const doses = [0.5, 5, 50, 500].map((concentration) => ({ concentration, response: 5 }));
    state.curves = [
      { ...curve("c1", R1, 1172.1), curve_class: "inactive", raw_data: doses },
      { ...curve("c2", R2, 12.5), raw_data: doses },
    ];
    await openDialog({ runIds: [R1, R2] });
    expect(screen.getByRole("cell", { name: "> 500 uM" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "12.5 uM" })).toBeInTheDocument();
  });

  it("says when the chosen runs have no curves for the compound", async () => {
    state.curves = [curve("c3", R3, 1)];
    await openDialog({ runIds: [R1] });
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

  it("keeps to the runs of the column's condition set that count", () => {
    const ds: Dataset = {
      revision: "r",
      level: "batches",
      row_count: 1,
      row_ids: [`${M1}:${B1}`],
      columns: [
        col("compound"),
        col("molecule_id", { hidden: true }),
        col("batch_id", { hidden: true }),
        col("dr:e", {
          kind: "number",
          provenance: { ...prov, aggregation: "geomean", run_ids: [R1, R3] },
        }),
      ],
      values: { compound: ["CEL-1"], molecule_id: [M1], batch_id: [B1], "dr:e": [0.5] },
    };
    // R3 is in the set but does not count (a draft); R2 counts but is the other set's.
    expect(curvesTarget(ds, "dr:e", 0, [R1, R2])).toEqual({
      ...target,
      runIds: [R1],
      batchId: B1,
    });
  });
});
