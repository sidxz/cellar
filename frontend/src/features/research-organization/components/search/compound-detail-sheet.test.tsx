import type { Molecule } from "@/features/chemical-registration/types";
import { CompoundCurvesProvider } from "@/features/screening-assay/components/compound-curves-dialog";
import type { Protocol } from "@/features/screening-assay/types";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useReportConfig } from "../../hooks/use-report-config";
import type { ActivityValue, CurveDetail } from "../../types";
import { CompoundDetailSheet } from "./compound-detail-sheet";

const curvesProps = vi.hoisted(() => [] as Array<Record<string, unknown>>);
vi.mock("@/features/screening-assay/components/multi-run-curves", () => ({
  MultiRunCurves: (props: Record<string, unknown>) => {
    curvesProps.push(props);
    return <div data-testid="multi-run-curves" />;
  },
}));

const mocks = vi.hoisted(() => ({ detail: vi.fn() }));
vi.mock("../../hooks/use-molecule-activity-detail", () => ({
  useMoleculeActivityDetail: () => mocks.detail(),
}));
vi.mock("@/shared/components/chemistry", () => ({ StructureThumbnail: () => null }));
vi.mock("@/shared/components/status-badge", () => ({ StatusBadge: () => null }));
vi.mock("@/shared/lib/plotly", () => ({
  Plot: () => <div data-testid="visible-curve">Dose–response plot</div>,
}));
const figureProps = vi.hoisted(() => [] as Array<Record<string, unknown>>);
vi.mock("@/features/screening-assay/components/dose-response-figure", () => ({
  DoseResponseFigure: (props: Record<string, unknown>) => {
    figureProps.push(props);
    return <div data-testid="overlay-figure" />;
  },
}));
vi.mock("@structflo/components/dose-response", () => ({
  MAX_OVERLAY_CURVES: 8,
  overlayColor: (i: number) => `colour-${i}`,
  buildDoseResponsePlot: () => ({ traces: [], layout: {}, config: {} }),
  DoseResponseSummaryCard: ({
    curve,
  }: { curve: { fitted_value: number; readout_definition_id: string } }) => (
    <div>
      Raw fit: {curve.fitted_value} · {curve.readout_definition_id}
    </div>
  ),
}));
const av: ActivityValue = {
  value: null,
  qualifier: "nd",
  unit: "uM",
  source: "dose_response",
  curve_type: "ic50",
  r_squared: 0.43,
  data_point_count: 8,
  raw_data: null,
  curve_params: null,
  // The runs the backend says the cell drew on; the drawer shows only these.
  run_ids: ["run"],
};
const molecule = {
  id: "mol",
  name: "Test",
  registration_number: "CC-test",
  activity: { "drc:rd": av },
} as unknown as Molecule & { activity: Record<string, ActivityValue> };
const protocols = [
  {
    id: "proto",
    name: "Target assay",
    readout_definitions: [
      {
        id: "rd",
        name: "Potency",
        dose_response_config: {
          intercepts: [{ kind: "ic", level: 50, basis: "relative_percent" }],
        },
      },
      { id: "other-rd", name: "Counter potency" },
    ],
  },
] as unknown as Protocol[];
const curve = {
  curve_id: "fit",
  run_id: "run",
  run_date: "2026-06-05",
  readout_definition_id: "rd",
  curve_type: "ic50",
  fitted_value: 1925,
  fitted_unit: "uM",
  r_squared: 0.43,
  curve_class: "inactive",
} as CurveDetail;
function setup(
  curves: CurveDetail[] = [curve],
  isError = false,
  reportedValue: ActivityValue = av,
) {
  mocks.detail.mockReturnValue({
    data: { protocols: [{ protocol_id: "proto", protocol_name: "Target assay", curves }] },
    isLoading: false,
    isError,
    refetch: vi.fn(),
  });
  const navigate = vi.fn();
  render(
    <CompoundDetailSheet
      molecule={{ ...molecule, activity: { "drc:rd": reportedValue } }}
      protocols={protocols}
      protocolColumns={["drc:rd"]}
      visibleProtocolIds={["proto"]}
      aggregationMode="gmean"
      currentIndex={0}
      totalCount={3}
      onNavigate={navigate}
      onOpenChange={() => {}}
    />,
  );
  return navigate;
}

describe("compound drawer evidence", () => {
  it("uses the search aggregate instead of recomputing across fetched fits", () => {
    setup(
      [
        { ...curve, fitted_value: 5, curve_class: "full" },
        { ...curve, curve_id: "fit-2", fitted_value: 20, curve_class: "full" },
      ],
      false,
      { ...av, value: 30, qualifier: "=", selection_rule: "geometric_mean" },
    );
    const reported = screen.getByRole("region", { name: "Reported search results" });
    expect(within(reported).getByText("30.00 uM")).toBeInTheDocument();
    expect(within(reported).queryByText("10.00 uM")).not.toBeInTheDocument();
  });
  it("keeps ND as the reported result and labels the fitted scalar as diagnostics", async () => {
    setup();
    const reported = screen.getByRole("region", { name: "Reported search results" });
    expect(within(reported).getByText("ND")).toBeInTheDocument();
    expect(within(reported).queryByText(/1925/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Raw fit:/)).not.toBeInTheDocument();
    expect(screen.getByTestId("visible-curve")).toBeVisible();
    fireEvent.click(screen.getByText("Fit parameters & diagnostics"));
    expect(await screen.findByText("Raw fit: 1925 · rd")).toBeInTheDocument();
    expect(screen.getByText(/Individual fit diagnostics/)).toBeInTheDocument();
    expect(within(reported).getByText("ND")).toBeInTheDocument();
  });
  it("keeps different readouts separate and leaves source-curve arrow keys alone", () => {
    const navigate = setup([
      curve,
      { ...curve, curve_id: "fit-2", readout_definition_id: "other-rd", fitted_value: 3 },
    ]);
    const picker = screen.getByRole("combobox", { name: "Source curve · Potency" });
    expect(
      screen.getByRole("combobox", { name: "Source curve · Counter potency" }),
    ).toBeInTheDocument();
    fireEvent.keyDown(picker, { key: "ArrowDown" });
    expect(navigate).not.toHaveBeenCalled();
  });
  it("keeps reported results visible when fetching source curves fails", () => {
    setup([], true);
    expect(
      within(screen.getByRole("region", { name: "Reported search results" })).getByText("ND"),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Source curves could not be loaded");
  });
});

describe("curves from the compound sheet", () => {
  it("offers Curves on the card of a protocol with measured curves and not on one without", () => {
    mocks.detail.mockReturnValue({
      data: {
        protocols: [
          { protocol_id: "proto", protocol_name: "Target assay", curves: [curve] },
          { protocol_id: "plain", protocol_name: "Plain assay", curves: [] },
        ],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    const withCurves = [
      { ...protocols[0], has_measured_curves: true },
      { ...protocols[0], id: "plain", name: "Plain assay", has_measured_curves: false },
    ];
    render(
      <CompoundCurvesProvider>
        <CompoundDetailSheet
          molecule={molecule}
          protocols={withCurves}
          protocolColumns={["drc:rd"]}
          visibleProtocolIds={["proto", "plain"]}
          currentIndex={0}
          totalCount={1}
          onNavigate={() => {}}
          onOpenChange={() => {}}
        />
      </CompoundCurvesProvider>,
    );
    const buttons = screen.getAllByRole("button", { name: "Traces" });
    expect(buttons).toHaveLength(1);
    // The card heading's expand button stays separate from Curves.
    expect(screen.getByRole("button", { name: /Target assay/ })).not.toContainElement(buttons[0]);
    fireEvent.click(buttons[0]);
    expect(
      screen.getByRole("dialog", {
        name: "Traces across runs",
        description: /^Target assay · CC-test\./,
      }),
    ).toBeInTheDocument();
    expect(curvesProps.at(-1)?.filter).toEqual({ moleculeIds: ["mol"] });
  });
});

describe("the drawer trusts the search's run set", () => {
  const options = (name: string) =>
    within(screen.getByRole("combobox", { name }))
      .getAllByRole("option")
      .map((o) => o.textContent);

  it("marks the cell's representative curve by id", () => {
    setup(
      [
        { ...curve, curve_id: "newer", run_id: "r2", run_date: "2026-07-01" },
        { ...curve, curve_id: "fit", run_id: "run" },
      ],
      false,
      { ...av, representative_curve_id: "fit", run_ids: ["r2", "run"] },
    );
    expect(screen.getByRole("combobox", { name: "Source curve · Potency" })).toHaveValue("fit");
  });

  it("hides curves from runs outside the cell's run set (rejected or filtered out)", () => {
    setup(
      [
        { ...curve, curve_id: "kept", run_id: "run" },
        { ...curve, curve_id: "rejected", run_id: "rejected-run", run_date: "2026-08-01" },
      ],
      false,
      { ...av, representative_curve_id: "kept", run_ids: ["run"] },
    );
    expect(options("Source curve · Potency")).toHaveLength(1);
  });

  it("labels a split protocol's curves with their group", () => {
    mocks.detail.mockReturnValue({
      data: {
        protocols: [
          {
            protocol_id: "proto",
            protocol_name: "Target assay",
            curves: [
              { ...curve, curve_id: "low", run_id: "r1", run_date: "2026-01-01" },
              { ...curve, curve_id: "high", run_id: "r2", run_date: "2026-02-01" },
            ],
          },
        ],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    render(
      <CompoundDetailSheet
        molecule={{
          ...molecule,
          activity: {
            "drc:rd@cond:10 µM": { ...av, run_ids: ["r1"] },
            "drc:rd@cond:1 mM": { ...av, run_ids: ["r2"] },
          },
        }}
        protocols={protocols}
        protocolColumns={["drc:rd"]}
        columnGroups={{
          proto: {
            split: { by: "condition", condition: "ATP" },
            groups: [
              { key: "cond:10 µM", label: "10 µM", run_ids: ["r1"], run_count: 1, flags: [] },
              { key: "cond:1 mM", label: "1 mM", run_ids: ["r2"], run_count: 1, flags: [] },
            ],
          },
        }}
        visibleProtocolIds={["proto"]}
        aggregationMode="latest"
        currentIndex={0}
        totalCount={1}
        onNavigate={vi.fn()}
        onOpenChange={() => {}}
      />,
    );
    const labels = options("Source curve · Potency");
    expect(labels.some((l) => l?.startsWith("1 mM ·"))).toBe(true);
    expect(labels.some((l) => l?.startsWith("10 µM ·"))).toBe(true);
    // Split values live per group in the grid; no single "reported" value here.
    expect(screen.queryByRole("region", { name: "Reported search results" })).toBeNull();
  });

  it("doesn't repeat a run split's date in the curve options", () => {
    mocks.detail.mockReturnValue({
      data: {
        protocols: [
          {
            protocol_id: "proto",
            protocol_name: "Target assay",
            curves: [{ ...curve, curve_id: "a", run_id: "r1", run_date: "2026-05-13" }],
          },
        ],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    render(
      <CompoundDetailSheet
        molecule={{ ...molecule, activity: { "drc:rd@run:r1": { ...av, run_ids: ["r1"] } } }}
        protocols={protocols}
        protocolColumns={["drc:rd"]}
        columnGroups={{
          proto: {
            split: { by: "run", condition: null },
            groups: [
              { key: "run:r1", label: "2026-05-13", run_ids: ["r1"], run_count: 1, flags: [] },
            ],
          },
        }}
        visibleProtocolIds={["proto"]}
        aggregationMode="latest"
        currentIndex={0}
        totalCount={1}
        onNavigate={vi.fn()}
        onOpenChange={() => {}}
      />,
    );
    expect(options("Source curve · Potency")[0]).toMatch(/^2026-05-13 · IC50/);
  });
});

describe("an overlaid protocol in the drawer", () => {
  const drawable: ActivityValue = {
    ...av,
    value: 1.3,
    qualifier: null,
    raw_data: [
      { x: 0.1, y: 5 },
      { x: 1, y: 50 },
      { x: 10, y: 95 },
    ],
    curve_params: {
      hill_slope: 1,
      top: 100,
      bottom: 0,
      num_points: 3,
      curve_class: "full",
      confidence_interval_low: null,
      confidence_interval_high: null,
      fit_quality_warnings: null,
    },
  } as ActivityValue;

  function renderSplit() {
    mocks.detail.mockReturnValue({
      data: {
        protocols: [
          {
            protocol_id: "proto",
            protocol_name: "Target assay",
            curves: [
              { ...curve, curve_id: "low", run_id: "r1", run_date: "2026-01-01" },
              { ...curve, curve_id: "high", run_id: "r2", run_date: "2026-02-01" },
            ],
          },
        ],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    render(
      <CompoundDetailSheet
        molecule={{
          ...molecule,
          activity: {
            "drc:rd@cond:10 µM": { ...drawable, run_ids: ["r1"] },
            "drc:rd@cond:1 mM": { ...drawable, value: 9.1, run_ids: ["r2"] },
          },
        }}
        protocols={protocols}
        protocolColumns={["drc:rd"]}
        columnGroups={{
          proto: {
            split: { by: "condition", condition: "ATP" },
            groups: [
              { key: "cond:10 µM", label: "10 µM", run_ids: ["r1"], run_count: 1, flags: [] },
              { key: "cond:1 mM", label: "1 mM", run_ids: ["r2"], run_count: 1, flags: [] },
            ],
          },
        }}
        visibleProtocolIds={["proto"]}
        aggregationMode="latest"
        currentIndex={0}
        totalCount={1}
        onNavigate={vi.fn()}
        onOpenChange={() => {}}
      />,
    );
  }

  beforeEach(() => {
    figureProps.length = 0;
  });
  afterEach(() => useReportConfig.getState().loadFromSavedSearch(null));

  it("draws every group's curve in one large plot when the grid overlays them", () => {
    useReportConfig
      .getState()
      .loadFromSavedSearch({ reportConfig: { displayPreset: "detailed", plotLayout: "overlay" } });
    renderSplit();
    const props = figureProps[figureProps.length - 1];
    expect(props.size).toBe("full");
    const curves = props.curves as { label: string; curve: { fitted_value: number } | null }[];
    expect(curves.map((c) => [c.label, c.curve?.fitted_value])).toEqual([
      ["10 µM", 1.3],
      ["1 mM", 9.1],
    ]);
    expect(screen.queryByTestId("visible-curve")).toBeNull();
    // Each fit stays inspectable.
    expect(
      within(screen.getByLabelText("Source curve · Potency")).getAllByRole("option"),
    ).toHaveLength(2);
  });

  it("keeps one source curve when the grid's plots are separate", () => {
    renderSplit();
    expect(figureProps).toHaveLength(0);
    expect(screen.getByTestId("visible-curve")).toBeInTheDocument();
  });
});

describe("a split protocol opened from one of its columns", () => {
  function renderFrom(focusColumn: string | null) {
    mocks.detail.mockReturnValue({
      data: {
        protocols: [
          {
            protocol_id: "proto",
            protocol_name: "Target assay",
            curves: [
              { ...curve, curve_id: "low", run_id: "r1", run_date: "2026-01-01" },
              { ...curve, curve_id: "high", run_id: "r2", run_date: "2026-02-01" },
            ],
          },
        ],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    render(
      <CompoundDetailSheet
        molecule={{
          ...molecule,
          activity: {
            "drc:rd@cond:10 µM": { ...av, run_ids: ["r1"], representative_curve_id: "low" },
            "drc:rd@cond:1 mM": { ...av, run_ids: ["r2"], representative_curve_id: "high" },
          },
        }}
        protocols={protocols}
        protocolColumns={["drc:rd"]}
        columnGroups={{
          proto: {
            split: { by: "condition", condition: "ATP" },
            groups: [
              { key: "cond:10 µM", label: "10 µM", run_ids: ["r1"], run_count: 1, flags: [] },
              { key: "cond:1 mM", label: "1 mM", run_ids: ["r2"], run_count: 1, flags: [] },
            ],
          },
        }}
        focusColumn={focusColumn}
        visibleProtocolIds={["proto"]}
        aggregationMode="latest"
        currentIndex={0}
        totalCount={1}
        onNavigate={vi.fn()}
        onOpenChange={() => {}}
      />,
    );
    return (screen.getByRole("combobox", { name: "Source curve · Potency" }) as HTMLSelectElement)
      .value;
  }

  it("shows the curve of the group whose column was clicked", () => {
    expect(renderFrom("drc:rd:plot@cond:10 µM")).toBe("low");
  });

  it("shows the other group's curve from the other group's column", () => {
    expect(renderFrom("drc:rd:ic:50@cond:1 mM")).toBe("high");
  });

  it("opens on the first group in header order from any other column", () => {
    expect(renderFrom("molecule")).toBe("low");
  });
});
