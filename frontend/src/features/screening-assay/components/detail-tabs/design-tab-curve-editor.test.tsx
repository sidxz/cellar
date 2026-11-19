import type { ReadoutUsageResponse } from "@/shared/lib/api/model";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Protocol } from "../../types";
import { DesignTab } from "./design-tab";

const remove = vi.hoisted(() => ({ mutate: vi.fn() }));
const usage = vi.hoisted(() => ({
  hook: vi.fn<(protocolId: string, enabled: boolean) => { data?: ReadoutUsageResponse[] }>(),
}));

vi.mock("../../hooks/use-protocols", () => {
  const idle = () => ({ mutate: vi.fn(), isPending: false });
  return {
    useAddReadoutDefinition: idle,
    useRemoveReadoutDefinition: () => ({ mutate: remove.mutate, isPending: false }),
    useUpdateReadoutDefinition: idle,
    useReadoutUsage: usage.hook,
    useProtocols: () => ({ data: [] }),
    useAddConditionDefinition: idle,
    useRemoveConditionDefinition: idle,
    useUpdateConditionDefinition: idle,
    useSetControlLayout: idle,
    useRemoveControlLayout: idle,
  };
});
vi.mock("../../hooks/use-plate-templates", () => ({ usePlateTemplates: () => ({ data: [] }) }));
vi.mock("@/shared/hooks/use-units", () => ({ useUnits: () => ({ data: [] }) }));
vi.mock("./protocol-control-convention-card", () => ({
  ProtocolControlConventionCard: () => null,
}));
vi.mock("../condition-group-table", () => ({ ConditionGroupTable: () => null }));
vi.mock("../temperature-window-dialog", () => ({ TemperatureWindowDialog: () => null }));
vi.mock("../../hooks/use-curve-positions", () => ({
  useCurvePositions: () => ({ data: undefined }),
}));
vi.mock("../plate-map-view", () => ({ PlateMapView: () => null }));
vi.mock("../readout-definition-viewer-dialog", () => ({
  ReadoutDefinitionViewerDialog: () => null,
}));

const readout = (id: string, name: string) => ({
  id,
  name,
  description: null,
  data_type: "numeric",
  unit: "AU",
  aggregation: "mean",
  precision: null,
  normalizations: [],
  is_calculated: false,
  calculation_formula: null,
  display_order: 0,
  pick_list_values: null,
  dose_response_config: null,
  melt_config: null,
});

const protocol = (over: object = {}) =>
  ({
    id: "p1",
    status: "active",
    is_locked: false,
    readout_definitions: [readout("used", "Signal"), readout("unused", "Sginal")],
    control_layouts: {},
    condition_definitions: [],
    ...over,
  }) as unknown as Protocol;

const curve = (y: string, y_normalization: string | null = null) => ({
  ...readout("ic50", "IC50"),
  data_type: "dose_response",
  unit: "µM",
  aggregation: "none",
  dose_response_config: {
    curve_type: "ic50",
    x_readout_name: null,
    y_readout_name: y,
    y_normalization,
    hill_slope_constraint: "unconstrained",
    normalization_scope: "per_plate",
    intercepts: [],
  },
});
const signal = (name: string, ...normalizations: string[]) => ({
  ...readout(name.toLowerCase(), name),
  normalizations,
});
const draft = (...readout_definitions: object[]) =>
  protocol({ status: "draft", readout_definitions });

const editCurve = () => {
  const cell = screen.getAllByText(/^IC50/)[0];
  fireEvent.click(within(cell.closest("tr") as HTMLElement).getByRole("button", { name: /^Edit/ }));
};
const save = () => screen.getByRole("button", { name: "Save" });

beforeEach(() => {
  usage.hook.mockReset();
  usage.hook.mockReturnValue({ data: [] });
});

describe("the curve editor shows the layer the fit really uses", () => {
  it("names the only layer instead of offering Raw signal", () => {
    render(
      <DesignTab
        protocol={draft(signal("Signal", "percent_inhibition"), curve("Signal"))}
        protocolId="p1"
      />,
    );
    editCurve();
    expect(screen.getByText("Fits the % Inhibition layer of Signal.")).toBeInTheDocument();
    expect(screen.queryByText("Raw signal")).not.toBeInTheDocument();
    expect(save()).toBeEnabled();
  });

  it("asks which layer when the Y readout calculates two, and holds Save until then", () => {
    render(
      <DesignTab
        protocol={draft(signal("Signal", "percent_inhibition", "z_score"), curve("Signal"))}
        protocolId="p1"
      />,
    );
    editCurve();
    expect(screen.getByText("Choose a layer")).toBeInTheDocument();
    expect(save()).toBeDisabled();
  });

  it("holds Save while the curve fits a readout that is gone, and says why", () => {
    render(
      <DesignTab
        protocol={draft(signal("THF Fluorescence Slope", "percent_inhibition"), curve("Signal"))}
        protocolId="p1"
      />,
    );
    editCurve();
    expect(
      screen.getByText(
        "'Signal' is not a numeric readout of this protocol. Choose the readout this curve fits.",
      ),
    ).toBeInTheDocument();
    expect(save()).toBeDisabled();
  });
});
