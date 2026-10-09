import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Protocol } from "../../types";
import { DesignTab } from "./design-tab";

const update = vi.hoisted(() => ({ mutate: vi.fn() }));

vi.mock("../../hooks/use-protocols", () => {
  const idle = () => ({ mutate: vi.fn(), isPending: false });
  return {
    useAddReadoutDefinition: idle,
    useRemoveReadoutDefinition: idle,
    useUpdateReadoutDefinition: idle,
    useProtocols: () => ({ data: [] }),
    useAddConditionDefinition: idle,
    useRemoveConditionDefinition: idle,
    useUpdateConditionDefinition: () => ({ mutate: update.mutate, isPending: false }),
    useSetControlLayout: idle,
    useRemoveControlLayout: idle,
  };
});
vi.mock("../../hooks/use-plate-templates", () => ({ usePlateTemplates: () => ({ data: [] }) }));
vi.mock("@/shared/hooks/use-units", () => ({ useUnits: () => ({ data: [] }) }));
vi.mock("./design-tab-protocol-card", () => ({ DesignTabProtocolCard: () => null }));
vi.mock("../condition-group-table", () => ({ ConditionGroupTable: () => null }));
vi.mock("../plate-map-view", () => ({ PlateMapView: () => null }));
vi.mock("./use-readout-definition-form", () => ({
  useReadoutDefinitionForm: () => ({}),
}));
vi.mock("./readout-definition-dialog", () => ({ ReadoutDefinitionDialog: () => null }));
vi.mock("../readout-definition-viewer-dialog", () => ({
  ReadoutDefinitionViewerDialog: () => null,
}));

const protocol = {
  id: "p1",
  status: "draft",
  is_locked: false,
  readout_definitions: [],
  control_layouts: [],
  condition_definitions: [
    {
      id: "c1",
      name: "S9",
      data_type: "pick_list",
      unit: null,
      pick_list_values: ["with", "without"],
    },
  ],
} as unknown as Protocol;

describe("DesignTab condition dialog", () => {
  it("saves a pick-list condition's edited values, and needs at least one", () => {
    render(<DesignTab protocol={protocol} protocolId="p1" />);
    const row = screen.getByText("S9").closest("tr") as HTMLElement;
    fireEvent.click(row.querySelectorAll("button")[0]);
    const box = screen.getByPlaceholderText("Type a value, press Enter");
    fireEvent.change(box, { target: { value: "both" } });
    fireEvent.keyDown(box, { key: "Enter" });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(update.mutate.mock.calls[0][0]).toEqual({
      definitionId: "c1",
      data: {
        name: "S9",
        data_type: "pick_list",
        unit: null,
        pick_list_values: ["with", "without", "both"],
      },
    });

    for (const v of ["with", "without", "both"]) {
      fireEvent.click(screen.getByRole("button", { name: `Remove ${v}` }));
    }
    expect(screen.getByText("Add at least one value.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });
});
