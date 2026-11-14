import type {
  DoseResponseConfig,
  InterceptSpec,
  Protocol,
  ReadoutDefinition,
} from "@/features/screening-assay/types";
import { MAX_OVERLAY_CURVES, overlayColor } from "@structflo/components/dose-response";
import type { ColDef, ColGroupDef } from "ag-grid-community";
import { describe, expect, it } from "vitest";
import { hasOverlayablePlots } from "../../lib/protocol-column-id";
import { buildDrcColumns, buildProtocolColumnGroups, resolveColumns } from "./results-grid";

const PROTO_ID = "11111111-1111-1111-1111-111111111111";
const RD_DR_ID = "22222222-2222-2222-2222-222222222222";
const RD_RAW_ID = "33333333-3333-3333-3333-333333333333";

function spec(over: Partial<InterceptSpec> = {}): InterceptSpec {
  return {
    kind: "ec",
    level: 50,
    basis: "relative_percent",
    label: null,
    ...over,
  };
}

function drConfig(intercepts: InterceptSpec[]): DoseResponseConfig {
  return {
    curve_type: "ec50",
    y_readout_name: "raw",
    x_readout_name: null,
    intercepts,
    hill_slope_constraint: "unconstrained",
    activity_threshold: null,
    normalization_scope: "per_plate",
    top_constraint: null,
    bottom_constraint: null,
    top_constraint_min: null,
    top_constraint_max: null,
    bottom_constraint_min: null,
    bottom_constraint_max: null,
    hill_slope_min: null,
    hill_slope_max: null,
    outlier_sigma: null,
  };
}

function rd(over: Partial<ReadoutDefinition> & { id: string }): ReadoutDefinition {
  const { id, ...rest } = over;
  return {
    id,
    name: "Readout",
    description: null,
    data_type: "numeric",
    unit: null,
    aggregation: "mean",
    precision: null,
    normalizations: [],
    is_calculated: false,
    calculation_formula: null,
    display_order: 0,
    pick_list_values: null,
    dose_response_config: null,
    ...rest,
  } as ReadoutDefinition;
}

function proto(rds: ReadoutDefinition[]): Protocol {
  return {
    id: PROTO_ID,
    name: "Mtb_WCA",
    readout_definitions: rds,
  } as unknown as Protocol;
}

describe("resolveColumns", () => {
  it("maps drc:<rd_id> back to the owning protocol", () => {
    const p = proto([
      rd({
        id: RD_DR_ID,
        data_type: "dose_response",
        dose_response_config: drConfig([spec({ level: 50 }), spec({ level: 90, label: "EC90" })]),
      }),
    ]);
    const resolved = resolveColumns([`drc:${RD_DR_ID}`], [p]);
    expect(resolved).toHaveLength(1);
    expect(resolved[0]).toMatchObject({
      colId: `drc:${RD_DR_ID}`,
      prefix: "drc",
      protocolId: PROTO_ID,
      readoutDefId: RD_DR_ID,
    });
  });

  it("uses parts[1] as protocol_id for 3-segment rd: colIds", () => {
    const p = proto([rd({ id: RD_RAW_ID })]);
    const resolved = resolveColumns([`rd:${PROTO_ID}:${RD_RAW_ID}`], [p]);
    expect(resolved).toHaveLength(1);
    expect(resolved[0]).toMatchObject({
      prefix: "rd",
      protocolId: PROTO_ID,
      readoutDefId: RD_RAW_ID,
    });
  });

  it("supports 4-segment rd:<proto>:<rd>:<norm> colIds", () => {
    const p = proto([rd({ id: RD_RAW_ID })]);
    const resolved = resolveColumns([`rd:${PROTO_ID}:${RD_RAW_ID}:percent_inhibition`], [p]);
    expect(resolved).toHaveLength(1);
    expect(resolved[0].protocolId).toBe(PROTO_ID);
    expect(resolved[0].readoutDefId).toBe(RD_RAW_ID);
  });

  it("falls back to readout-def reverse index for legacy 2-segment rd: colIds", () => {
    const p = proto([rd({ id: RD_RAW_ID })]);
    const resolved = resolveColumns([`rd:${RD_RAW_ID}`], [p]);
    expect(resolved).toHaveLength(1);
    expect(resolved[0].protocolId).toBe(PROTO_ID);
  });

  it("drops colIds with no resolvable protocol", () => {
    expect(resolveColumns(["drc:not-a-real-rd"], [proto([])])).toHaveLength(0);
    expect(resolveColumns(["pro:foo:bar"], [proto([])])).toHaveLength(0);
  });
});

describe("buildDrcColumns", () => {
  it("emits one column per protocol intercept plus a Plot column", () => {
    const dr = rd({
      id: RD_DR_ID,
      data_type: "dose_response",
      dose_response_config: drConfig([spec({ level: 50 }), spec({ level: 90, label: "EC90" })]),
    });
    const cols = buildDrcColumns(`drc:${RD_DR_ID}`, proto([dr]), RD_DR_ID);
    expect(cols).toHaveLength(3);
    expect(cols[0].headerName).toBe("EC50");
    expect(cols[1].headerName).toBe("EC90");
    expect(cols[2].headerName).toBe("Plot");
    expect(cols[0].colId).toBe(`drc:${RD_DR_ID}:ec:50`);
    expect(cols[1].colId).toBe(`drc:${RD_DR_ID}:ec:90`);
    expect(cols[2].colId).toBe(`drc:${RD_DR_ID}:plot`);
  });

  it("falls back to a single anonymous value column when no intercepts declared", () => {
    const dr = rd({
      id: RD_DR_ID,
      name: "Resazurin",
      data_type: "dose_response",
      dose_response_config: null,
    });
    const cols = buildDrcColumns(`drc:${RD_DR_ID}`, proto([dr]), RD_DR_ID);
    expect(cols).toHaveLength(2);
    expect(cols[0].headerName).toBe("Resazurin");
    expect(cols[0].colId).toBe(`drc:${RD_DR_ID}:value`);
    expect(cols[1].headerName).toBe("Plot");
  });
});

describe("buildProtocolColumnGroups — split protocols", () => {
  const drRd = rd({
    id: RD_DR_ID,
    name: "IC50",
    data_type: "dose_response",
    dose_response_config: drConfig([spec({ kind: "ic", level: 50 })]),
  });
  const protocol = proto([drRd, rd({ id: RD_RAW_ID, name: "Signal" })]);
  const groups = {
    [PROTO_ID]: {
      split: { by: "condition" as const, condition: "ATP" },
      groups: [
        { key: "cond:10 µM", label: "10 µM", run_ids: [], run_count: 2, flags: [] },
        { key: "cond:1 mM", label: "1 mM", run_ids: [], run_count: 1, flags: [] },
      ],
    },
  };
  const leaves = (g: ColGroupDef) =>
    (g.children as (ColDef | ColGroupDef)[]).flatMap((c) =>
      "children" in c ? (c.children as ColDef[]) : [c as ColDef],
    );

  it("nests one header group per split group, in the backend's order", () => {
    const [group] = buildProtocolColumnGroups(
      [`drc:${RD_DR_ID}`],
      [protocol],
      "latest",
      groups,
    ) as ColGroupDef[];
    expect(group.headerName).toBe("Mtb_WCA · by ATP");
    const sub = group.children as ColGroupDef[];
    expect(sub.map((g) => g.headerName)).toEqual(["10 µM · 2 runs", "1 mM · 1 run"]);
  });

  it("reads each group's cells from its own activity key", () => {
    const [group] = buildProtocolColumnGroups(
      [`drc:${RD_DR_ID}`, `rd:${PROTO_ID}:${RD_RAW_ID}`],
      [protocol],
      "latest",
      groups,
    ) as ColGroupDef[];
    const ids = leaves(group).map((c) => c.colId);
    expect(ids).toContain(`drc:${RD_DR_ID}:ic:50@cond:10 µM`);
    expect(ids).toContain(`drc:${RD_DR_ID}:plot@cond:1 mM`);
    expect(ids).toContain(`rd:${PROTO_ID}:${RD_RAW_ID}@cond:1 mM`);
    const readout = leaves(group).find((c) => c.colId === `rd:${PROTO_ID}:${RD_RAW_ID}@cond:1 mM`);
    const row = { activity: { [`rd:${PROTO_ID}:${RD_RAW_ID}@cond:1 mM`]: { value: 7 } } };
    // biome-ignore lint/suspicious/noExplicitAny: AG Grid valueGetter params
    expect((readout?.valueGetter as any)({ data: row })).toBe(7);
  });

  it("marks a rejected hand-picked run in its header", () => {
    const [group] = buildProtocolColumnGroups([`drc:${RD_DR_ID}`], [protocol], "latest", {
      [PROTO_ID]: {
        split: { by: "run" as const, condition: null },
        groups: [
          {
            key: "run:r1",
            label: "2026-03-01",
            run_ids: ["r1"],
            run_count: 1,
            flags: ["rejected"],
          },
        ],
      },
    }) as ColGroupDef[];
    expect((group.children as ColGroupDef[])[0].headerName).toBe("2026-03-01 (rejected)");
  });

  it("shows one muted column when no runs match the split", () => {
    const [group] = buildProtocolColumnGroups([`drc:${RD_DR_ID}`], [protocol], "latest", {
      [PROTO_ID]: { split: { by: "condition" as const, condition: "ATP" }, groups: [] },
    }) as ColGroupDef[];
    const children = group.children as ColDef[];
    expect(children).toHaveLength(1);
    expect(children[0].headerName).toBe("No runs match");
  });

  it("overlays every group's curve in one plot column after the groups", () => {
    const [group] = buildProtocolColumnGroups(
      [`drc:${RD_DR_ID}`],
      [protocol],
      "latest",
      groups,
      "overlay",
    ) as ColGroupDef[];
    const children = group.children as (ColDef | ColGroupDef)[];
    const sub = children.filter((c): c is ColGroupDef => "children" in c);
    expect(sub.map((g) => g.headerGroupComponentParams?.color)).toEqual([
      overlayColor(0),
      overlayColor(1),
    ]);
    expect(leaves(group).map((c) => c.colId)).toEqual([
      `drc:${RD_DR_ID}:ic:50@cond:10 µM`,
      `drc:${RD_DR_ID}:ic:50@cond:1 mM`,
      `drc:${RD_DR_ID}:plot@overlay`,
    ]);
  });

  it("keeps side-by-side plots by default", () => {
    const [group] = buildProtocolColumnGroups(
      [`drc:${RD_DR_ID}`],
      [protocol],
      "latest",
      groups,
    ) as ColGroupDef[];
    expect(leaves(group).map((c) => c.colId)).toEqual([
      `drc:${RD_DR_ID}:ic:50@cond:10 µM`,
      `drc:${RD_DR_ID}:plot@cond:10 µM`,
      `drc:${RD_DR_ID}:ic:50@cond:1 mM`,
      `drc:${RD_DR_ID}:plot@cond:1 mM`,
    ]);
    expect((group.children as ColGroupDef[])[0].headerGroupComponent).toBeUndefined();
  });

  it("stays side by side past the overlay's colour limit, and says why", () => {
    const many = Array.from({ length: MAX_OVERLAY_CURVES + 1 }, (_, i) => ({
      key: `cond:${i} µM`,
      label: `${i} µM`,
      run_ids: [],
      run_count: 1,
      flags: [],
    }));
    const [group] = buildProtocolColumnGroups(
      [`drc:${RD_DR_ID}`],
      [protocol],
      "latest",
      {
        [PROTO_ID]: { split: { by: "condition" as const, condition: "ATP" }, groups: many },
      },
      "overlay",
    ) as ColGroupDef[];
    expect(leaves(group).some((c) => c.colId === `drc:${RD_DR_ID}:plot@overlay`)).toBe(false);
    expect(leaves(group).filter((c) => c.colId?.startsWith(`drc:${RD_DR_ID}:plot@`))).toHaveLength(
      MAX_OVERLAY_CURVES + 1,
    );
    expect(group.headerTooltip).toContain(`more than ${MAX_OVERLAY_CURVES}`);
  });

  it("knows when a search has curves to overlay", () => {
    expect(hasOverlayablePlots([`drc:${RD_DR_ID}`], [protocol], groups)).toBe(true);
    expect(hasOverlayablePlots([`drc:${RD_DR_ID}`], [protocol], null)).toBe(false);
    expect(hasOverlayablePlots([`rd:${PROTO_ID}:${RD_RAW_ID}`], [protocol], groups)).toBe(false);
    const many = Array.from({ length: MAX_OVERLAY_CURVES + 1 }, (_, i) => ({
      key: `cond:${i}`,
      label: `${i}`,
      run_ids: [],
      run_count: 1,
      flags: [],
    }));
    expect(
      hasOverlayablePlots([`drc:${RD_DR_ID}`], [protocol], {
        [PROTO_ID]: { split: { by: "condition" as const, condition: "ATP" }, groups: many },
      }),
    ).toBe(false);
  });

  it("fills the overlay plot from each group's own cell, in header order", () => {
    const rd2 = rd({
      id: "44444444-4444-4444-4444-444444444444",
      name: "IC90 curve",
      data_type: "dose_response",
      dose_response_config: drConfig([spec({ kind: "ic", level: 90 })]),
    });
    const two = proto([drRd, rd2, rd({ id: RD_RAW_ID, name: "Signal" })]);
    const [group] = buildProtocolColumnGroups(
      [`drc:${RD_DR_ID}`, `drc:${rd2.id}`, `rd:${PROTO_ID}:${RD_RAW_ID}`],
      [two],
      "latest",
      groups,
      "overlay",
    ) as ColGroupDef[];
    const plots = leaves(group).filter((c) => c.colId?.endsWith("@overlay"));
    expect(plots.map((c) => c.headerName)).toEqual(["Plot · IC50", "Plot · IC90 curve"]);
    expect(leaves(group).map((c) => c.colId)).toContain(`rd:${PROTO_ID}:${RD_RAW_ID}@cond:1 mM`);
    const cell = { value: 1.3 };
    const row = { activity: { [`drc:${RD_DR_ID}@cond:10 µM`]: cell } };
    // biome-ignore lint/suspicious/noExplicitAny: AG Grid renderer params
    const element = (plots[0].cellRenderer as any)({ data: row });
    expect(element.props.entries).toEqual([
      { value: cell, label: "10 µM" },
      { value: undefined, label: "1 mM" },
    ]);
  });

  it("leaves unsplit protocols as they are", () => {
    const [group] = buildProtocolColumnGroups(
      [`drc:${RD_DR_ID}`],
      [protocol],
      "latest",
      null,
    ) as ColGroupDef[];
    expect(group.headerName).toBe("Mtb_WCA");
    expect((group.children as ColDef[]).map((c) => c.colId)).toEqual([
      `drc:${RD_DR_ID}:ic:50`,
      `drc:${RD_DR_ID}:plot`,
    ]);
  });
});

describe("single-point cells", () => {
  it("show ND, not the no-data dash, when no run gave a reportable value", async () => {
    const { render, screen } = await import("@testing-library/react");
    const [group] = buildProtocolColumnGroups(
      [`rd:${PROTO_ID}:${RD_RAW_ID}`],
      [proto([rd({ id: RD_RAW_ID, name: "MIC" })])],
      "latest",
      null,
    ) as ColGroupDef[];
    const column = (group.children as ColDef[])[0];
    const row = {
      activity: {
        [`rd:${PROTO_ID}:${RD_RAW_ID}`]: { value: null, qualifier: "nd", source: "readout" },
      },
    };
    // biome-ignore lint/suspicious/noExplicitAny: AG Grid renderer params
    render((column.cellRenderer as any)({ data: row }));
    expect(screen.getByText("ND")).toBeInTheDocument();
  });
});

describe("wide tables", () => {
  const A = "44444444-4444-4444-4444-444444444444";
  const B = "55555555-5555-5555-5555-555555555555";
  const C = "66666666-6666-6666-6666-666666666666";
  const main = { window: "Main", channel_key: "ratio", low: 50, high: 85 };
  const thermal = proto([
    rd({ id: A, name: "Inflection Point #1 for Ratio", unit: "°C", display_order: 1 }),
    rd({
      id: B,
      name: "Tm (Main)",
      unit: "°C",
      display_order: 2,
      melt_config: { ...main, measure: "tm" },
    }),
    rd({
      id: C,
      name: "Max ΔTm (Main)",
      unit: "°C",
      display_order: 3,
      melt_config: { ...main, measure: "max_delta_tm" },
    }),
  ]);
  const thermalCols = [A, B, C].map((id) => `rd:${PROTO_ID}:${id}`);
  const build = (cols: string[], p: Protocol) =>
    buildProtocolColumnGroups(cols, [p], "latest", null) as ColGroupDef[];
  // biome-ignore lint/suspicious/noExplicitAny: AG Grid renderer params
  const renderCell = (column: ColDef, row: unknown) => (column.cellRenderer as any)({ data: row });

  it("groups a thermal protocol by window with the Activity tab's labels, every readout shown", () => {
    const [group] = build(thermalCols, thermal);
    const sub = group.children as ColGroupDef[];
    expect(sub.map((g) => g.headerName)).toEqual(["Main window · 50–85 °C", "Other readouts"]);
    expect((sub[0].children as ColDef[]).map((c) => c.headerName)).toEqual([
      "Max ΔTm (°C)",
      "Tm (°C)",
    ]);
    expect(sub.flatMap((g) => g.children)).toHaveLength(3);
  });

  it("opens every group, and folds a group to its headline only on request", () => {
    const [group] = build(thermalCols, thermal);
    const window = (group.children as ColGroupDef[])[0];
    expect([group.openByDefault, window.openByDefault]).toEqual([true, true]);
    expect((window.children as ColDef[]).map((c) => c.columnGroupShow)).toEqual([
      undefined,
      "open",
    ]);
  });

  it("folds a dose-response block to its primary intercept and its plot", () => {
    const dr = rd({
      id: RD_DR_ID,
      name: "EC50",
      data_type: "dose_response",
      dose_response_config: drConfig([spec(), spec({ level: 90 })]),
    });
    const [group] = build([`drc:${RD_DR_ID}`], proto([dr]));
    expect((group.children as ColDef[]).map((c) => c.columnGroupShow)).toEqual([
      undefined,
      "open",
      undefined,
    ]);
  });

  it("says 'no result' once for an assay the compound has nothing in", async () => {
    const { render, screen } = await import("@testing-library/react");
    const [group] = build(thermalCols, thermal);
    const [first, second] = (group.children as ColGroupDef[])[0].children as ColDef[];
    expect(renderCell(second, { activity: {} })).toBeNull();
    render(renderCell(first, { activity: {} }));
    expect(screen.getByText("no result")).toBeInTheDocument();
  });

  it("leaves the header's unit out of the cell, but keeps a different one", async () => {
    const { render, screen } = await import("@testing-library/react");
    const [group] = build(
      [`rd:${PROTO_ID}:${RD_RAW_ID}`],
      proto([rd({ id: RD_RAW_ID, name: "MIC", unit: "µg/mL" })]),
    );
    const column = (group.children as ColDef[])[0];
    const cell = (unit: string) => ({
      activity: {
        [`rd:${PROTO_ID}:${RD_RAW_ID}`]: { value: 1.5, qualifier: "=", unit, source: "readout" },
      },
    });
    const { unmount } = render(renderCell(column, cell("ug/mL")));
    expect(screen.getByText("1.500")).toBeInTheDocument();
    unmount();
    render(renderCell(column, cell("mg/L")));
    expect(screen.getByText("1.500 mg/L")).toBeInTheDocument();
  });
});
