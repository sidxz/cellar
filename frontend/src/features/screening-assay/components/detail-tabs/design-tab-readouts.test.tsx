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

const USAGE: ReadoutUsageResponse[] = [
  {
    readout_definition_id: "used",
    in_use: true,
    reasons: ["has values in 3 runs", "used by a column of 2 campaigns"],
  },
  { readout_definition_id: "unused", in_use: false, reasons: [] },
];

const row = (name: string) => screen.getByText(name).closest("tr") as HTMLElement;
const editButton = (name: string) => within(row(name)).getByRole("button", { name: /^Edit/ });
const deleteButton = (name: string) => within(row(name)).queryByRole("button", { name: "Delete" });

beforeEach(() => {
  remove.mutate.mockClear();
  usage.hook.mockReset();
  usage.hook.mockReturnValue({ data: USAGE });
});

describe("DesignTab readouts of a published protocol", () => {
  it("lets an unused readout be removed and fully edited", () => {
    render(<DesignTab protocol={protocol()} protocolId="p1" />);
    expect(usage.hook).toHaveBeenCalledWith("p1", true);

    fireEvent.click(deleteButton("Sginal") as HTMLElement);
    expect(remove.mutate).toHaveBeenCalledWith("unused");

    expect(editButton("Sginal")).toHaveAttribute("title", "Edit");
    fireEvent.click(editButton("Sginal"));
    expect(screen.getByDisplayValue("Sginal")).toBeEnabled();
    expect(
      screen.getByText("Nothing uses this readout yet, so every field can still be changed."),
    ).toBeInTheDocument();
  });

  it("keeps a used readout to cosmetic edits and says what uses it", () => {
    render(<DesignTab protocol={protocol()} protocolId="p1" />);
    expect(deleteButton("Signal")).not.toBeInTheDocument();

    const title = editButton("Signal").getAttribute("title") ?? "";
    expect(title).toContain("has values in 3 runs; used by a column of 2 campaigns");
    expect(title).toContain("new version");

    fireEvent.click(editButton("Signal"));
    expect(screen.getByDisplayValue("Signal")).toBeDisabled();
    expect(screen.getByDisplayValue("AU")).toBeEnabled();
    expect(
      screen.getByText(/In use: has values in 3 runs; used by a column of 2 campaigns\./),
    ).toBeInTheDocument();
  });

  it("offers only the cosmetic edit until the usage has loaded", () => {
    usage.hook.mockReturnValue({ data: undefined });
    render(<DesignTab protocol={protocol()} protocolId="p1" />);
    expect(deleteButton("Sginal")).not.toBeInTheDocument();
    fireEvent.click(editButton("Sginal"));
    expect(screen.getByDisplayValue("Sginal")).toBeDisabled();
  });

  it("never removes the last readout", () => {
    usage.hook.mockReturnValue({ data: [USAGE[1]] });
    render(
      <DesignTab
        protocol={protocol({ readout_definitions: [readout("unused", "Sginal")] })}
        protocolId="p1"
      />,
    );
    expect(deleteButton("Sginal")).toBeDisabled();
  });
});

describe("DesignTab readouts elsewhere", () => {
  it("leaves a draft as it was: every readout edits fully and removes, usage unread", () => {
    render(<DesignTab protocol={protocol({ status: "draft" })} protocolId="p1" />);
    expect(usage.hook).toHaveBeenCalledWith("p1", false);
    for (const name of ["Signal", "Sginal"]) {
      expect(deleteButton(name)).toBeInTheDocument();
      expect(editButton(name)).toHaveAttribute("title", "Edit");
    }
    fireEvent.click(editButton("Signal"));
    expect(screen.getByDisplayValue("Signal")).toBeEnabled();
    expect(screen.getByText("Update fields on this readout.")).toBeInTheDocument();
  });

  it("leaves a locked protocol as it was: nothing edits or removes, usage unread", () => {
    render(<DesignTab protocol={protocol({ is_locked: true })} protocolId="p1" />);
    expect(usage.hook).toHaveBeenCalledWith("p1", false);
    for (const name of ["Signal", "Sginal"]) {
      expect(deleteButton(name)).not.toBeInTheDocument();
      expect(within(row(name)).queryByRole("button", { name: /^Edit/ })).not.toBeInTheDocument();
    }
  });

  it("leaves a retired protocol as it was", () => {
    render(<DesignTab protocol={protocol({ status: "retired" })} protocolId="p1" />);
    expect(usage.hook).toHaveBeenCalledWith("p1", false);
    expect(deleteButton("Sginal")).not.toBeInTheDocument();
  });
});
