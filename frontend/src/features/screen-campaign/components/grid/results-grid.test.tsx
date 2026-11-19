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
  StageOutcome,
} from "../../types";
import { emptyFilters } from "../campaign-filter-bar";
import {
  CompoundValueCell,
  type CompoundValueCellProps,
  MeasurementFacts,
  NotDeterminedCell,
  RemoveSelectedButton,
  ResultsGridV2,
  StageColumnHeader,
  StageGroupHeader,
  curveFramesByChannel,
  isEmptyColumn,
  isReportedEndpoint,
} from "./results-grid";

// ResultsGridV2 hands its column defs to DataGrid; the mock keeps them for
// the header tests below instead of mounting AG Grid.
const { grid } = vi.hoisted(() => ({
  grid: { columnDefs: [] as (ColDef | ColGroupDef)[] },
}));
vi.mock("@/shared/components/data-grid/data-grid", () => ({
  DataGrid: (props: { columnDefs: (ColDef | ColGroupDef)[] }) => {
    grid.columnDefs = props.columnDefs;
    return null;
  },
}));
vi.mock("@/features/chemical-registration", () => ({
  useMoleculesByIds: () => ({ data: { items: [] } }),
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
    expect(screen.getByText("reported")).toHaveAttribute(
      "title",
      "Reported endpoint — no fitted curve for this compound",
    );
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

  it("keeps the chip on the marker line beside the verdict chip", () => {
    renderCell({ reported: true, verdict: "pass" });
    const chip = screen.getByText("reported");
    const markerLine = chip.parentElement;
    expect(markerLine).toHaveTextContent("pass");
    // Value stays on its own line above the markers so the 120px column
    // never clips it.
    expect(markerLine).not.toHaveTextContent("13.6");
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

const STAGE = "stage-1";

function row(id: string, outcome: StageOutcome) {
  return {
    result: {
      id,
      molecule_id: `mol-${id}`,
      measurements: [],
      stage_outcomes: [{ stage_id: STAGE, outcome, overridden: false, checks: [] }],
    },
  };
}

function renderToolbar(stageOutcomes: StageOutcome[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RemoveSelectedButton
        campaignId="c1"
        rows={[row("r-hit", "hit"), row("r-miss", "miss")] as never}
        filters={{ ...emptyFilters(), stageOutcomes: new Set(stageOutcomes) }}
        selectedStageId={STAGE}
      />
    </QueryClientProvider>,
  );
}

describe("RemoveSelectedButton visible selection", () => {
  beforeEach(() => mutate.mockClear());

  it("removes every selected row when no chip filter is on", () => {
    renderToolbar([]);
    fireEvent.click(screen.getByRole("button", { name: "Remove selected (2)" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove 2" }));
    expect(mutate).toHaveBeenCalledWith({
      campaignId: "c1",
      data: { result_ids: ["r-hit", "r-miss"] },
    });
  });

  it("leaves a selected row the chip filter hides untouched", () => {
    // AG Grid keeps r-miss selected after the "Hit" chip hides it; the
    // chemist can't see it, so it must not be removed — nor counted.
    renderToolbar(["hit"]);
    fireEvent.click(screen.getByRole("button", { name: "Remove selected (1)" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove 1" }));
    expect(mutate).toHaveBeenCalledWith({ campaignId: "c1", data: { result_ids: ["r-hit"] } });
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

describe("StageColumnHeader", () => {
  it("shows the readout, its short label beneath, and the full label with its parts on hover", () => {
    const tooltip = columnTooltip(describedColumn, "Kinase Panel");
    render(<StageColumnHeader readout="% Inhibition" shortLabel={SHORT} tooltip={tooltip} />);

    expect(screen.getByText("% Inhibition")).toBeInTheDocument();
    const header = screen.getByText(SHORT).parentElement as HTMLElement;
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

  it("tells same-day runs apart the way the stage list does, wrapping inside the card", () => {
    const dl = facts(measurement);
    const line = screen.getByText("created 09:05 · run-1").closest("li") as HTMLElement;
    expect(line).toHaveTextContent("Kinase Panel · Run on Nov 12, 2026created 09:05 · run-1");
    expect(line).not.toHaveClass("truncate");
    expect(dl.className).toContain("minmax(0,1fr)");
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
          filters={emptyFilters()}
          selectedStageId={null}
          readOnly
        />
      </QueryClientProvider>,
    );
    const group = grid.columnDefs.find(
      (c) => "groupId" in c && c.groupId === "stage_st-retest",
    ) as ColGroupDef;
    return { group, value: group.children.find((c) => "colId" in c && c.colId === "ch-1_value") };
  }

  it("line 1 is the column's own (renamed) name, line 2 the short label", () => {
    const params = (columnDefs().value as ColDef).headerComponentParams;
    expect(params.innerHeaderComponent).toBe(StageColumnHeader);
    const Header = params.innerHeaderComponent as ComponentType<
      typeof params.innerHeaderComponentParams
    >;
    render(<Header {...params.innerHeaderComponentParams} />);

    expect(screen.getByText("Retest inhibition")).toBeInTheDocument();
    expect(screen.queryByText("% Inhibition")).not.toBeInTheDocument();
    expect(screen.getByText(SHORT)).toBeInTheDocument();
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

  function renderGrid() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ResultsGridV2
          campaign={campaign}
          filters={emptyFilters()}
          selectedStageId={null}
          readOnly
        />
      </QueryClientProvider>,
    );
  }
  const group = (id: string) =>
    grid.columnDefs.find((c) => "groupId" in c && c.groupId === id) as ColGroupDef;
  const colIds = (id: string) => group(id).children.map((c) => (c as ColDef).colId);
  const headerParams = (id: string) =>
    group(id).headerGroupComponentParams.innerHeaderGroupComponentParams;

  it("hides a column with no values yet, its curve with it, behind a chip on the stage", () => {
    renderGrid();
    expect(colIds("stage_st-1")).toEqual(["ch-inh_value"]);
    expect(group("stage_st-1").headerGroupComponentParams.innerHeaderGroupComponent).toBe(
      StageGroupHeader,
    );
    expect(headerParams("stage_st-1")).toMatchObject({ emptyCount: 1, showingEmpty: false });
  });

  it("keeps a stage whose columns are all empty on the grid as one placeholder", () => {
    renderGrid();
    expect(colIds("stage_st-2")).toEqual(["st-2_empty"]);
    expect(headerParams("stage_st-2").emptyCount).toBe(1);
  });

  it("shows a stage's empty columns from its chip and remembers that per viewer", () => {
    renderGrid();
    render(<StageGroupHeader {...headerParams("stage_st-1")} />);
    fireEvent.click(screen.getByRole("button", { name: "+1 empty column" }));

    expect(colIds("stage_st-1")).toEqual(["ch-inh_value", "ch-ic50_value", "ch-ic50_curve"]);
    expect(colIds("stage_st-2")).toEqual(["st-2_empty"]); // the other stage is untouched
    expect(JSON.parse(localStorage.getItem("campaign-empty-columns:c-empty") ?? "")).toEqual([
      "st-1",
    ]);

    // A fresh page reads the choice back.
    cleanup();
    renderGrid();
    expect(headerParams("stage_st-1").showingEmpty).toBe(true);
    expect(colIds("stage_st-1")).toContain("ch-ic50_value");
  });

  it("names the chip by what it does", () => {
    const { rerender } = render(
      <StageGroupHeader
        title="Primary"
        emptyCount={2}
        showingEmpty={false}
        onToggleEmpty={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "+2 empty columns" })).toBeInTheDocument();
    rerender(
      <StageGroupHeader title="Primary" emptyCount={2} showingEmpty onToggleEmpty={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "Hide 2 empty columns" })).toBeInTheDocument();
    rerender(
      <StageGroupHeader
        title="Primary"
        emptyCount={0}
        showingEmpty={false}
        onToggleEmpty={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
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
