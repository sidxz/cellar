import type { ColumnDescriptionResponse } from "@/shared/lib/api/model";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ColDef, ColGroupDef } from "ag-grid-community";
import type { ComponentType } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { columnTooltip } from "../../lib/column-description";
import type {
  CampaignChannelResponse,
  CampaignMeasurementResponse,
  CampaignResponse,
} from "../../types";
import { emptyFilters } from "../campaign-filter-bar";
import {
  CompoundValueCell,
  type CompoundValueCellProps,
  MeasurementFacts,
  NotDeterminedCell,
  ProtocolGroupHeader,
  ReadoutColumnHeader,
  RemoveSelectedButton,
  ResultsGridV2,
  SelectLinks,
  blanksLast,
  curveFramesByChannel,
  curveOwnerIds,
  isEmptyColumn,
  isReportedEndpoint,
  unitsByChannel,
} from "./results-grid";

// ResultsGridV2 hands its column defs to DataGrid; the mock keeps them for
// the header tests below instead of mounting AG Grid.
const { grid } = vi.hoisted(() => ({
  grid: { columnDefs: [] as (ColDef | ColGroupDef)[], enableMultiSelect: false as unknown },
}));
vi.mock("@/shared/components/data-grid/data-grid", () => ({
  DataGrid: (props: { columnDefs: (ColDef | ColGroupDef)[]; enableMultiSelect?: unknown }) => {
    grid.columnDefs = props.columnDefs;
    grid.enableMultiSelect = props.enableMultiSelect;
    return null;
  },
}));
vi.mock("@/features/chemical-registration", () => ({
  useMoleculesByIds: () => ({ data: { items: [] } }),
}));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useMemberNames: () => () => "Ada",
}));
vi.mock("../../hooks/use-campaign-curves", () => ({
  useCampaignCurves: () => ({ data: new Map() }),
}));
vi.mock("@/features/screening-assay", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useProtocolSummaries: () => ({ data: [{ id: "proto-1", name: "Kinase Panel" }] }),
}));

vi.mock("@/features/inventory/hooks/use-batches", () => ({
  useBatchesByMolecule: () => ({ data: [{ id: "b-1", batch_number: "B-007" }] }),
}));
vi.mock("../../hooks/use-campaign-run-labels", () => ({
  useCampaignRunLabels: () => (id: string) => ({
    protocolName: "Kinase Panel",
    text: id === "run-1" ? "Run on Nov 12, 2026" : "Run on Nov 14, 2026",
    detail: id === "run-1" ? "created 09:05 · run-1" : "",
  }),
}));

/** Every leaf column, however deep its groups nest. */
function leaves(defs: (ColDef | ColGroupDef)[]): ColDef[] {
  return defs.flatMap((c) => ("children" in c ? leaves(c.children) : [c as ColDef]));
}

function renderCell(overrides: Partial<CompoundValueCellProps> = {}) {
  return render(
    <CompoundValueCell
      prefix=""
      value={13.6}
      unit="uM"
      replicates={null}
      verdict={null}
      overridden={false}
      overrideReason={null}
      reported={false}
      readOnly
      onEdit={() => {}}
      {...overrides}
    />,
  );
}

describe("CompoundValueCell reported marker", () => {
  it("shows the reported chip for a DR measurement sourced from an endpoint row", () => {
    const reported = isReportedEndpoint(true, { source_readout_id: "rd-1", source_curve_id: null });
    expect(reported).toBe(true);

    renderCell({ reported });
    expect(screen.getByText("reported")).toBeInTheDocument();
  });

  it("shows no chip for a DR measurement backed by a fitted curve", () => {
    const reported = isReportedEndpoint(true, { source_readout_id: null, source_curve_id: "c-1" });
    expect(reported).toBe(false);

    renderCell({ reported });
    expect(screen.queryByText("reported")).toBeNull();
  });

  it("shows no chip on a non-DR channel even when a readout id is present", () => {
    const reported = isReportedEndpoint(false, {
      source_readout_id: "rd-1",
      source_curve_id: null,
    });
    expect(reported).toBe(false);

    renderCell({ reported });
    expect(screen.queryByText("reported")).toBeNull();
  });
});

// ── Bulk remove ───────────────────────────────────────────────────────────────

const { mutate } = vi.hoisted(() => ({ mutate: vi.fn() }));

vi.mock("@/shared/lib/api/campaigns/campaigns", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useBulkRemoveResultRowsApiV1CampaignsCampaignIdResultsBulkRemovePost: () => ({
    mutate,
    isPending: false,
  }),
}));

function renderRemove(resultIds: string[], hiddenCount = 0) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RemoveSelectedButton campaignId="c1" resultIds={resultIds} hiddenCount={hiddenCount} />
    </QueryClientProvider>,
  );
}

describe("RemoveSelectedButton", () => {
  beforeEach(() => mutate.mockClear());

  it("removes exactly the ticked rows", () => {
    renderRemove(["r-hit", "r-miss"]);
    fireEvent.click(screen.getByRole("button", { name: "Remove selected (2)" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove 2" }));
    expect(mutate).toHaveBeenCalledWith({
      campaignId: "c1",
      data: { result_ids: ["r-hit", "r-miss"] },
    });
  });

  it("says when the filters hide some of them before removing", () => {
    renderRemove(["r-hit", "r-miss"], 1);
    fireEvent.click(screen.getByRole("button", { name: "Remove selected (2)" }));
    expect(screen.getByText(/2 selected rows, 1 hidden by filters/)).toBeInTheDocument();
  });

  it("is off with nothing ticked", () => {
    renderRemove([]);
    expect(screen.getByRole("button", { name: "Remove selected (0)" })).toBeDisabled();
  });
});

// ── Stage column header ──────────────────────────────────────────────────────

const LABEL =
  "Retest · % Inhibition · single concentration 10 µM · mean of 3 replicates · 3 runs · mean across runs";
const SHORT = "single concentration 10 µM · mean of 3 replicates · 3 runs · mean across runs";

const describedColumn = {
  id: "ch-1",
  label: "% Inhibition",
  description: {
    stage_name: "Retest",
    readout_label: "% Inhibition",
    design: "single_concentration",
    concentrations: [{ value: 10, unit: "µM", count: 40 }],
    replicates: { min: 3, max: 3, not_recorded: 0 },
    run_count: 3,
    rule: "mean across runs",
    basis: ["reported"],
    needs_concentration: false,
    label: LABEL,
    short_label: SHORT,
    value_count: 40,
  },
} as unknown as CampaignChannelResponse;

describe("ReadoutColumnHeader", () => {
  it("shows the column's name and dose, and the full label with its parts on hover", () => {
    const tooltip = columnTooltip(describedColumn, "Kinase Panel");
    render(<ReadoutColumnHeader label="% Inhibition" at="10 µM" tooltip={tooltip} />);

    expect(screen.getByText("at 10 µM")).toBeInTheDocument();
    expect(screen.queryByText(SHORT)).toBeNull();
    const header = screen.getByText("% Inhibition").parentElement as HTMLElement;
    const lines = (header.getAttribute("title") ?? "").split("\n");
    expect(lines[0]).toBe(LABEL);
    expect(lines).toEqual(
      expect.arrayContaining([
        "Stage: Retest",
        "Protocol: Kinase Panel",
        "Concentration: 10 µM",
        "Replicates: 3",
        "Runs: 3",
        "Rule: mean across runs",
      ]),
    );
  });
});

describe("ProtocolGroupHeader", () => {
  it("says how each column was measured behind its ⓘ, not in the header", () => {
    render(<ProtocolGroupHeader name="Kinase Panel" channels={[describedColumn]} />);
    expect(screen.queryByText(SHORT)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "How Kinase Panel was measured" }));
    expect(screen.getByText(SHORT)).toBeInTheDocument();
  });

  it("offers no ⓘ when no column says how it was measured", () => {
    render(<ProtocolGroupHeader name="Kinase Panel" channels={[]} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});

// ── Untested cells ───────────────────────────────────────────────────────────

describe("NotDeterminedCell", () => {
  it("says quietly why a cell is untested", () => {
    render(<NotDeterminedCell unresolvedReason="several_concentrations" />);
    expect(screen.getByText("ND")).toHaveAttribute(
      "title",
      "Measured at several concentrations — choose one for this column",
    );
  });

  it("keeps the generic ND explanation when there is no reason", () => {
    render(<NotDeterminedCell unresolvedReason={null} />);
    expect(screen.getByText("ND").getAttribute("title")).toMatch(/^ND = Not Determined/);
  });
});

// ── Cell facts ───────────────────────────────────────────────────────────────

describe("MeasurementFacts", () => {
  const measurement = {
    channel_id: "ch-1",
    value: 42,
    test_concentration_value: 10,
    test_concentration_unit: "µM",
    replicate_count: null,
    contributing_run_ids: ["run-1", "run-2"],
    batch_ids: ["b-1"],
    basis: "reported",
    concentration_series: false,
  } as unknown as CampaignMeasurementResponse;

  function facts(m: CampaignMeasurementResponse) {
    render(
      <MeasurementFacts
        measurement={m}
        moleculeId="mol-1"
        campaign={{ id: "c1" } as unknown as CampaignResponse}
      />,
    );
    return screen.getByText("Concentration").closest("dl") as HTMLElement;
  }

  it("lists concentration, n, basis, batches and the runs behind the value", () => {
    const dl = facts(measurement);
    expect(dl).toHaveTextContent("Concentration10 µM");
    expect(dl).toHaveTextContent("nnot recorded");
    expect(dl).toHaveTextContent("Basisreported");
    expect(dl).toHaveTextContent("BatchesB-007");
    expect(dl).toHaveTextContent("Runs2");
    expect(screen.getByRole("link", { name: "Run on Nov 12, 2026" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Run on Nov 14, 2026" })).toBeInTheDocument();
  });

  it("tells same-day runs apart the way the stage list does", () => {
    facts(measurement);
    const line = screen.getByText("created 09:05 · run-1").closest("li") as HTMLElement;
    expect(line).toHaveTextContent("Kinase Panel · Run on Nov 12, 2026created 09:05 · run-1");
  });

  it("calls a dose-response value a concentration series and leaves n out", () => {
    const dl = facts({ ...measurement, concentration_series: true, basis: "measured" });
    expect(dl).toHaveTextContent("Concentrationconcentration series");
    expect(dl).not.toHaveTextContent("not recorded");
    expect(dl).toHaveTextContent("Basismeasured");
  });
});

describe("CompoundValueCell facts", () => {
  it("opens the value's facts from the value itself", () => {
    renderCell({ facts: <span>the facts</span> });
    fireEvent.click(screen.getByRole("button", { name: "13.6 uM" }));
    expect(screen.getByText("the facts")).toBeInTheDocument();
  });
});

describe("ResultsGridV2 column headers", () => {
  const renamed = {
    ...describedColumn,
    label: "Retest inhibition",
    protocol_id: "proto-1",
    readout_definition_id: "rd-1",
    source_kind: "readout_data",
    selection_rule: "mean_across_runs",
    display_order: 0,
    stage_id: "st-retest",
  } as unknown as CampaignChannelResponse;
  const stageName = "Retest at three concentrations, confirmed by a second operator";
  const campaign = {
    id: "c1",
    stages: [
      {
        id: "st-retest",
        name: stageName,
        parent_stage_id: null,
        display_order: 0,
        kind: "criteria",
        criteria: [],
      },
    ],
    channels: [renamed],
    results: [{ id: "r1", molecule_id: "mol-1", measurements: [], stage_outcomes: [] }],
  } as unknown as CampaignResponse;

  function columnDefs() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ResultsGridV2
          campaign={campaign}
          onFiltersChange={vi.fn()}
          filters={emptyFilters()}
          selectedStageId={null}
          readOnly
        />
      </QueryClientProvider>,
    );
    const group = grid.columnDefs.find(
      (c) => "groupId" in c && c.groupId === "stage_st-retest",
    ) as ColGroupDef;
    const protocol = group.children[0] as ColGroupDef;
    return {
      group,
      protocol,
      value: leaves(group.children).find((c) => c.colId === "ch-1_value"),
    };
  }

  it("puts each column under its protocol, inside its stage", () => {
    const { protocol } = columnDefs();
    expect(protocol.headerGroupComponentParams.innerHeaderGroupComponent).toBe(ProtocolGroupHeader);
    expect(protocol.headerGroupComponentParams.innerHeaderGroupComponentParams.name).toBe(
      "Kinase Panel",
    );
    expect(leaves(protocol.children).map((c) => c.colId)).toEqual(["ch-1_value"]);
  });

  it("heads a value column with the column's own (renamed) name, not the readout", () => {
    const params = (columnDefs().value as ColDef).headerComponentParams;
    expect(params.innerHeaderComponent).toBe(ReadoutColumnHeader);
    const Header = params.innerHeaderComponent as ComponentType<
      typeof params.innerHeaderComponentParams
    >;
    render(<Header {...params.innerHeaderComponentParams} />);

    expect(screen.getByText("Retest inhibition")).toBeInTheDocument();
    expect(screen.queryByText("% Inhibition")).not.toBeInTheDocument();
    expect(screen.queryByText(SHORT)).not.toBeInTheDocument();
  });

  it("names a stage group on hover, since a long name over one column clips", () => {
    expect(columnDefs().group.headerTooltip).toBe(stageName);
  });
});

describe("ResultsGridV2 empty columns", () => {
  const noValues: ColumnDescriptionResponse = {
    ...(describedColumn.description as ColumnDescriptionResponse),
    concentrations: [],
    replicates: { min: null, max: null, not_recorded: 0 },
    run_count: 0,
    basis: [],
    short_label: "no values yet",
    value_count: 0,
  };
  const base = {
    protocol_id: "proto-1",
    selection_rule: "latest_run",
    stage_id: "st-1",
  };
  const inhibition = {
    ...describedColumn,
    ...base,
    id: "ch-inh",
    readout_definition_id: "rd-inh",
    source_kind: "readout_data",
    display_order: 0,
  } as unknown as CampaignChannelResponse;
  // A dose-response column a mirrored protocol put on a single-dose stage.
  const ic50 = {
    ...base,
    id: "ch-ic50",
    label: "IC50",
    readout_definition_id: "rd-ic50",
    source_kind: "dose_response_curve",
    display_order: 1,
    description: noValues,
  } as unknown as CampaignChannelResponse;
  const stage = (id: string, name: string, order: number) => ({
    id,
    name,
    parent_stage_id: null,
    display_order: order,
    kind: "criteria",
    criteria: [],
  });
  const campaign = {
    id: "c-empty",
    stages: [stage("st-1", "Primary", 0), stage("st-2", "Retest", 1)],
    channels: [inhibition, ic50, { ...ic50, id: "ch-retest", stage_id: "st-2", display_order: 2 }],
    results: [{ id: "r1", molecule_id: "mol-1", measurements: [], stage_outcomes: [] }],
  } as unknown as CampaignResponse;

  beforeEach(() => localStorage.clear());

  function renderGrid(selectedStageId: string | null = null) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ResultsGridV2
          campaign={campaign}
          onFiltersChange={vi.fn()}
          filters={emptyFilters()}
          selectedStageId={selectedStageId}
          readOnly
        />
      </QueryClientProvider>,
    );
  }
  const group = (id: string) =>
    grid.columnDefs.find((c) => "groupId" in c && c.groupId === id) as ColGroupDef | undefined;
  const colIds = (id: string) => leaves(group(id)?.children ?? []).map((c) => c.colId);
  const stages = () =>
    grid.columnDefs.flatMap((c) => ("groupId" in c && c.groupId ? [c.groupId] : []));

  it("shows every stage under All, and only the picked stage's columns when one is picked", () => {
    renderGrid();
    expect(stages()).toEqual(["stage_st-1"]); // st-2's one column is empty, so hidden
    cleanup();
    renderGrid("st-1");
    expect(stages()).toEqual(["stage_st-1"]);
    cleanup();
    renderGrid("st-2");
    expect(stages()).toEqual([]);
  });

  it("starts a column with no values yet hidden, its curve with it", () => {
    renderGrid();
    expect(colIds("stage_st-1")).toEqual(["ch-inh_value"]);
    expect(screen.getByRole("button", { name: "Columns, 4 hidden" })).toBeInTheDocument();
  });

  it("shows an empty column once the viewer ticks it, and remembers that per campaign", () => {
    renderGrid();
    fireEvent.click(screen.getByRole("button", { name: "Columns, 4 hidden" }));
    const ic50Value = screen.getAllByRole("checkbox")[3] as HTMLElement; // structure, notes, inh, ic50
    fireEvent.click(ic50Value);
    expect(colIds("stage_st-1")).toEqual(["ch-inh_value", "ch-ic50_value"]);
    expect(JSON.parse(localStorage.getItem("campaign-columns:c-empty") ?? "")).toEqual({
      hidden: [],
      shown: ["ch-ic50"],
    });

    // A fresh page reads the choice back.
    cleanup();
    renderGrid();
    expect(colIds("stage_st-1")).toEqual(["ch-inh_value", "ch-ic50_value"]);
  });

  it("hides any column, the structure too, and shows them all again", () => {
    renderGrid();
    fireEvent.click(screen.getByRole("button", { name: "Columns, 4 hidden" }));
    fireEvent.click(screen.getAllByRole("checkbox")[0] as HTMLElement); // Structure
    expect(grid.columnDefs.some((c) => "colId" in c && c.colId === "structure")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Show all" }));
    expect(grid.columnDefs.some((c) => "colId" in c && c.colId === "structure")).toBe(true);
    expect(colIds("stage_st-1")).toEqual(["ch-inh_value", "ch-ic50_value", "ch-ic50_curve"]);
    expect(stages()).toEqual(["stage_st-1", "stage_st-2"]);
  });

  it("hides a column with no value anywhere — unfilled or all ND — but never one waiting for a dose", () => {
    expect(isEmptyColumn(ic50)).toBe(true);
    // Measured, but every cell ND: runs behind it, still nothing to show.
    const allNd = { ...noValues, run_count: 2, short_label: "dose-response · 2 runs" };
    expect(isEmptyColumn({ ...ic50, description: allNd })).toBe(true);
    expect(isEmptyColumn({ ...ic50, description: { ...allNd, value_count: 1 } })).toBe(false);
    expect(
      isEmptyColumn({ ...ic50, description: { ...noValues, needs_concentration: true } }),
    ).toBe(false);
    expect(isEmptyColumn({ ...ic50, description: null })).toBe(false);
  });
});

describe("curveFramesByChannel", () => {
  const snapshot = (y: number) => ({
    fitted_value: 1,
    top: 100,
    bottom: 0,
    hill_slope: 1,
    raw_data: [
      { x: 0.01, y },
      { x: 10, y },
    ],
  });
  const measure = (channel_id: string, y: number) =>
    ({ channel_id, curve_snapshot: snapshot(y) }) as unknown as CampaignMeasurementResponse;
  const channel = (id: string, readout_definition_id: string) =>
    ({
      id,
      protocol_id: "p1",
      readout_definition_id,
      source_kind: "dose_response_curve",
    }) as unknown as CampaignChannelResponse;
  const protocols = new Map([
    [
      "p1",
      {
        readout_definitions: [
          { id: "sig", name: "Signal", normalizations: ["percent_inhibition"] },
          { id: "raw", name: "Raw", normalizations: [] },
          {
            id: "ic50",
            name: "IC50",
            dose_response_config: { y_readout_name: "Signal", y_normalization: null },
          },
          {
            id: "rawfit",
            name: "Raw fit",
            dose_response_config: { y_readout_name: "Raw", y_normalization: null },
          },
        ],
      },
    ],
  ]);
  const results = [
    { measurements: [measure("c1", 85), measure("c2", 1000)] },
    { measurements: [measure("c1", 90), measure("c2", 3000)] },
  ] as unknown as CampaignResponse["results"];

  it("gives a % curve column its 0 % and 100 % anchors over every row", () => {
    const frames = curveFramesByChannel(
      [channel("c1", "ic50")],
      results ?? [],
      new Map(),
      protocols,
    );
    expect(frames.get("c1")?.yRange).toEqual([-10, 110]);
    expect(frames.get("c1")?.xRange?.[1]).toBeCloseTo(10 * Math.sqrt(10), 9);
  });

  it("spans every contributing curve and every drawn excluded point", () => {
    const aggregate = {
      channel_id: "c1",
      curve_snapshot: {
        ...snapshot(50),
        raw_data: [
          { x: 1, y: 50 },
          { x: 10, y: 60 },
        ],
        excluded_points: [{ x: 5, y: 150 }],
        additional_curves: [
          {
            fitted_value: 1,
            top: 140,
            bottom: -20,
            hill_slope: 1,
            run_date: "2026-01-01",
            raw_data: [
              { x: 0.00001, y: -20 },
              { x: 1000, y: 140 },
            ],
          },
        ],
      },
    } as unknown as CampaignMeasurementResponse;
    const frames = curveFramesByChannel(
      [channel("c1", "ic50")],
      [{ measurements: [aggregate] }] as unknown as CampaignResponse["results"] & object,
      new Map(),
      protocols,
    );
    const [x0, x1] = frames.get("c1")?.xRange ?? [];
    expect(x0).toBeCloseTo(0.00001 / Math.sqrt(10), 12);
    expect(x1).toBeCloseTo(1000 * Math.sqrt(10), 6);
    expect(frames.get("c1")?.yRange).toEqual([-37, 167]);
  });

  it("frames on the layer the snapshot says it fits; an older snapshot asks the protocol", () => {
    const fitted = (layer: string | null, y: number) =>
      ({
        channel_id: "c1",
        curve_snapshot: { ...snapshot(y), fitted_layer: layer },
      }) as unknown as CampaignMeasurementResponse;
    const frame = (...ms: CampaignMeasurementResponse[]) =>
      curveFramesByChannel(
        [channel("c1", "ic50")],
        ms.map((m) => ({ measurements: [m] })) as unknown as CampaignResponse["results"] & object,
        new Map(),
        protocols,
      ).get("c1")?.yRange;
    // The protocol says % (ic50 on Signal), but these curves were fitted raw.
    expect(frame(fitted(null, 1000), fitted(null, 3000))).toEqual([900, 3100]);
    // A snapshot frozen before the key existed: the protocol's layer.
    expect(frame(measure("c1", 85))).toEqual([-10, 110]);
  });

  it("fits a raw-signal curve column to its data", () => {
    const frames = curveFramesByChannel(
      [channel("c2", "rawfit")],
      results ?? [],
      new Map(),
      protocols,
    );
    expect(frames.get("c2")?.yRange).toEqual([900, 3100]);
  });
});

describe("ResultsGridV2 on a campaign another app manages", () => {
  const campaign = {
    id: "c-managed",
    stages: [],
    channels: [],
    results: [{ id: "r1", molecule_id: "mol-1", measurements: [], stage_outcomes: [] }],
  } as unknown as CampaignResponse;

  function renderGrid(rowsLocked: boolean) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ResultsGridV2
          campaign={campaign}
          onFiltersChange={vi.fn()}
          filters={emptyFilters()}
          selectedStageId={null}
          readOnly={false}
          rowsLocked={rowsLocked}
        />
      </QueryClientProvider>,
    );
  }

  it("offers no compound removal while rows are locked, but still ticks rows for QC", () => {
    renderGrid(true);
    expect(grid.enableMultiSelect).toBe(true);
    expect(screen.queryByRole("button", { name: /^Remove selected/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Mark QC verified…" })).toBeDisabled();
  });

  it("keeps compound removal on a campaign ChemCellar manages", () => {
    renderGrid(false);
    expect(screen.getByRole("button", { name: "Remove selected (0)" })).toBeDisabled();
  });

  it("offers no ticks to someone with no bulk gesture", () => {
    cleanup();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ResultsGridV2
          campaign={campaign}
          onFiltersChange={vi.fn()}
          filters={emptyFilters()}
          selectedStageId={null}
          readOnly
        />
      </QueryClientProvider>,
    );
    expect(grid.enableMultiSelect).toBe(false);
    expect(screen.queryByText(/^Bulk/)).toBeNull();
  });
});

describe("ResultsGridV2 QC under the value", () => {
  const channel = {
    id: "ch-q",
    label: "Inhibition",
    protocol_id: "proto-1",
    readout_definition_id: "rd-q",
    selection_rule: "latest_run",
    stage_id: null,
    source_kind: "readout_data",
    display_order: 0,
  } as unknown as CampaignChannelResponse;

  function renderValueCell(m: Partial<CampaignMeasurementResponse>, qcReadOnly = false) {
    const campaign = {
      id: "c-qc",
      stages: [],
      channels: [channel],
      results: [
        {
          id: "r1",
          molecule_id: "mol-1",
          measurements: [{ id: "m1", channel_id: "ch-q", qc_verdict: "not_tested", ...m }],
          stage_outcomes: [],
        },
      ],
    } as unknown as CampaignResponse;
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ResultsGridV2
          campaign={campaign}
          onFiltersChange={vi.fn()}
          filters={emptyFilters()}
          selectedStageId={null}
          readOnly={false}
          qcReadOnly={qcReadOnly}
        />
      </QueryClientProvider>,
    );
    const col = leaves(grid.columnDefs).find((c) => c.colId === "ch-q_value") as ColDef;
    const Renderer = col.cellRenderer as ComponentType<unknown>;
    const params = { data: { result: campaign.results[0] } };
    return render(
      <QueryClientProvider client={qc}>
        <Renderer {...(params as object)} />
      </QueryClientProvider>,
    );
  }

  it("stacks a verdict, who set it, when, and its note under the value", () => {
    const { container } = renderValueCell({
      value: 5,
      value_qualifier: "=",
      qc_verdict: "verified",
      qc_verdict_by: "u-1",
      qc_verdict_at: "2026-11-20T10:00:00Z",
      qc_verdict_note: "clean plate",
      holds_result: true,
    });
    expect(container.textContent).toMatch(/^5.*QC verified.*Ada.*clean plate$/);
  });

  it("adds no QC lines under a value nobody has checked", () => {
    const { container } = renderValueCell({ value: 5, value_qualifier: "=", holds_result: true });
    expect(container.textContent).toBe("5");
  });

  it("keeps QC under a tested ND too", () => {
    renderValueCell({
      value: null,
      value_qualifier: "nd",
      qc_verdict: "failed",
      holds_result: true,
    });
    expect(screen.getByText("QC failed")).toBeInTheDocument();
  });

  it("sets QC from the value cell's right-click menu", () => {
    renderValueCell({ value: 5, value_qualifier: "=", holds_result: true });
    fireEvent.contextMenu(screen.getByText("5"));
    expect(screen.getByRole("menuitem", { name: "Mark QC verified" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Add QC note…" })).toBeInTheDocument();
  });

  it("offers a QC viewer no right-click menu", () => {
    renderValueCell({ value: 5, value_qualifier: "=", holds_result: true }, true);
    fireEvent.contextMenu(screen.getByText("5"));
    expect(screen.queryByRole("menuitem")).toBeNull();
  });

  it("gives a viewer the verdict but no QC buttons", () => {
    renderValueCell({ value: null, value_qualifier: "nd", holds_result: true }, true);
    fireEvent.click(screen.getByRole("button", { name: "ND" }));
    expect(screen.getByText("Not tested")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Verified" })).toBeNull();
  });

  it("opens the QC control from a tested ND", () => {
    renderValueCell({ value: null, value_qualifier: "nd", holds_result: true });
    fireEvent.click(screen.getByRole("button", { name: "ND" }));
    expect(screen.getByRole("button", { name: "Verified" })).toBeInTheDocument();
  });
});

describe("ResultsGridV2 notes column", () => {
  const campaign = {
    id: "c-notes",
    stages: [],
    channels: [],
    results: [
      {
        id: "r1",
        molecule_id: "mol-1",
        notes: "Watch hERG",
        notes_edited_by: "u-1",
        notes_edited_at: "2026-11-21T14:03:00Z",
        measurements: [],
        stage_outcomes: [],
      },
    ],
  } as unknown as CampaignResponse;

  function renderNotesCell(flags: { readOnly: boolean; notesReadOnly?: boolean }) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ResultsGridV2
          campaign={campaign}
          onFiltersChange={vi.fn()}
          filters={emptyFilters()}
          selectedStageId={null}
          {...flags}
        />
      </QueryClientProvider>,
    );
    const col = grid.columnDefs.find((c) => (c as ColDef).colId === "notes") as ColDef;
    const Renderer = col.cellRenderer as ComponentType<unknown>;
    const params = { data: { result: campaign.results[0] } };
    return render(
      <QueryClientProvider client={qc}>
        <Renderer {...(params as object)} />
      </QueryClientProvider>,
    );
  }

  it("lets an editor write a note on a campaign whose curation is locked", () => {
    renderNotesCell({ readOnly: true, notesReadOnly: false });
    expect(screen.getByRole("button", { name: "Edit note" })).toBeInTheDocument();
  });

  it("follows readOnly when no notes flag is given", () => {
    renderNotesCell({ readOnly: true });
    expect(screen.getByText("Watch hERG")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit note" })).toBeNull();
  });

  it("opens the note's editor in a window from the cell", () => {
    renderNotesCell({ readOnly: false });
    fireEvent.click(screen.getByRole("button", { name: "Edit note" }));
    expect(screen.getByRole("dialog", { name: "Edit note" })).toBeInTheDocument();
  });
});

describe("grid helpers", () => {
  it("sorts ND and blank last, low to high and high to low", () => {
    const values = [3, null, 1, 2];
    const asc = [...values].sort((a, b) => blanksLast(a, b, null, null, false));
    expect(asc).toEqual([1, 2, 3, null]);
    // AG Grid flips the comparator's result for a descending sort.
    const desc = [...values].sort((a, b) => -blanksLast(a, b, null, null, true));
    expect(desc).toEqual([3, 2, 1, null]);
  });

  it("draws one curve per readout per stage, on its first dose-response channel", () => {
    const ch = (id: string, rd: string, kind = "dose_response_curve") =>
      ({ id, readout_definition_id: rd, source_kind: kind }) as CampaignChannelResponse;
    const owners = curveOwnerIds([
      { channels: [ch("ec50", "rd-1"), ch("ec90", "rd-1"), ch("pct", "rd-2", "readout_data")] },
      { channels: [ch("retest-ec50", "rd-1")] },
    ]);
    expect([...owners]).toEqual(["ec50", "retest-ec50"]);
  });

  it("gives a channel the unit most of its exact values carry", () => {
    const m = (channel_id: string, unit: string, value_qualifier = "=") =>
      ({ channel_id, unit, value: 1, value_qualifier }) as CampaignMeasurementResponse;
    const units = unitsByChannel([
      { measurements: [m("a", "µM"), m("b", "-")] },
      { measurements: [m("a", "µM"), m("b", "nM", "<")] },
      { measurements: [m("a", "nM")] },
    ] as unknown as CampaignResponse["results"]);
    expect(units.get("a")).toBe("µM");
    // A limit is not an exact value, so it never sets the unit.
    expect(units.get("b")).toBe("-");
  });
});

describe("ResultsGridV2 search", () => {
  it("applies a search on submit, not on every keystroke", () => {
    const onFiltersChange = vi.fn();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ResultsGridV2
          campaign={
            {
              id: "c-search",
              stages: [],
              channels: [],
              results: [{ id: "r1", molecule_id: "mol-1", measurements: [], stage_outcomes: [] }],
            } as unknown as CampaignResponse
          }
          filters={emptyFilters()}
          onFiltersChange={onFiltersChange}
          selectedStageId={null}
          readOnly
        />
      </QueryClientProvider>,
    );
    const box = screen.getByRole("textbox", { name: "Search compound ID, name or alias" });
    fireEvent.change(box, { target: { value: "  sacc " } });
    expect(onFiltersChange).not.toHaveBeenCalled();
    fireEvent.submit(box);
    expect(onFiltersChange).toHaveBeenCalledWith(expect.objectContaining({ search: "sacc" }));
  });
});

describe("SelectLinks", () => {
  const renderLinks = (props: Partial<Parameters<typeof SelectLinks>[0]>) => {
    const handlers = { onSelectVisible: vi.fn(), onSelectAll: vi.fn(), onClear: vi.fn() };
    render(
      <SelectLinks
        visible={12}
        total={80}
        allVisibleTicked={false}
        allTicked={false}
        anyTicked={false}
        {...handlers}
        {...props}
      />,
    );
    return handlers;
  };
  const links = () => screen.queryAllByRole("button").map((b) => b.textContent);

  it("offers the visible rows and the whole table while filters hide some", () => {
    const h = renderLinks({});
    expect(links()).toEqual(["Select all 12 visible", "Select all 80 in the table"]);
    fireEvent.click(screen.getByRole("button", { name: "Select all 12 visible" }));
    expect(h.onSelectVisible).toHaveBeenCalled();
  });

  it("offers one select-all when nothing is filtered out", () => {
    renderLinks({ visible: 80 });
    expect(links()).toEqual(["Select all 80"]);
  });

  it("drops what would change nothing, and offers to clear once anything is ticked", () => {
    const h = renderLinks({ allVisibleTicked: true, anyTicked: true });
    expect(links()).toEqual(["Select all 80 in the table", "Clear selection"]);
    fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(h.onClear).toHaveBeenCalled();
    cleanup();
    renderLinks({ allTicked: true, allVisibleTicked: true, anyTicked: true });
    expect(links()).toEqual(["Clear selection"]);
  });
});
