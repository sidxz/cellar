import type { Molecule } from "@/features/chemical-registration/types";
import { CompoundCurvesProvider } from "@/features/screening-assay/components/compound-curves-dialog";
import type { Protocol } from "@/features/screening-assay/types";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ActivityValue, CurveDetail } from "../../types";
import { CompoundDetailSheet, findSearchSourceCurve } from "./compound-detail-sheet";

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
vi.mock("@structflo/components/dose-response", () => ({
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
      currentQuery={null}
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
          currentQuery={null}
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

describe("matching a plotted source to the search snapshot", () => {
  const source = {
    ...curve,
    top: 100,
    bottom: 0,
    hill_slope: 1,
    confidence_interval_low: 10,
    confidence_interval_high: 30,
  };
  const snapshot = {
    ...av,
    value: 30,
    curve_params: {
      top: 100,
      bottom: 0,
      hill_slope: 1,
      num_points: 8,
      curve_class: "inactive",
      confidence_interval_low: 10,
      confidence_interval_high: 30,
    },
  };
  it("matches fit metadata even when the reported value is an aggregate", () => {
    expect(
      findSearchSourceCurve([{ ...source, curve_id: "newer", hill_slope: 2 }, source], snapshot)
        ?.curve_id,
    ).toBe("fit");
  });
  it("does not claim an ambiguous or missing fit is the report source", () => {
    expect(
      findSearchSourceCurve([source, { ...source, curve_id: "duplicate" }], snapshot),
    ).toBeNull();
    expect(findSearchSourceCurve([source], av)).toBeNull();
  });
  it("uses the exact curve ID for an explicitly single-run report", () => {
    expect(
      findSearchSourceCurve([source], {
        ...av,
        run_count: 1,
        runs: [
          {
            run_id: "run",
            curve_id: "fit",
            run_date: "2026-06-05",
            curve_class: "inactive",
            r_squared: 0.43,
            intercept_values: [],
          },
        ],
      })?.curve_id,
    ).toBe("fit");
  });
});
