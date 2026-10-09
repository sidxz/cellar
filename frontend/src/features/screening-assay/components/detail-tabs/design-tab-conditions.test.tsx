import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Protocol } from "../../types";
import { DesignTab } from "./design-tab";

const update = vi.hoisted(() => ({ mutate: vi.fn() }));
const add = vi.hoisted(() => ({ mutate: vi.fn() }));

vi.mock("../../hooks/use-protocols", () => {
  const idle = () => ({ mutate: vi.fn(), isPending: false });
  return {
    useAddReadoutDefinition: idle,
    useRemoveReadoutDefinition: idle,
    useUpdateReadoutDefinition: idle,
    useProtocols: () => ({ data: [] }),
    useAddConditionDefinition: () => ({ mutate: add.mutate, isPending: false }),
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
      fixed_value: null,
    },
    {
      id: "c2",
      name: "Incubation time",
      data_type: "numeric",
      unit: "h",
      pick_list_values: null,
      fixed_value: "72",
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
        fixed_value: null,
      },
    });

    for (const v of ["with", "without", "both"]) {
      fireEvent.click(screen.getByRole("button", { name: `Remove ${v}` }));
    }
    expect(screen.getByText("Add at least one value.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("shows a fixed value with its unit, and one that varies per run", () => {
    render(<DesignTab protocol={protocol} protocolId="p1" />);
    expect(screen.getByText("72 h")).toBeInTheDocument();
    expect(screen.getByText("Varies per run")).toBeInTheDocument();
  });

  it("edits a fixed value", () => {
    render(<DesignTab protocol={protocol} protocolId="p1" />);
    const row = screen.getByText("Incubation time").closest("tr") as HTMLElement;
    fireEvent.click(row.querySelectorAll("button")[0]);
    const fixed = screen.getByLabelText("Fixed for this protocol");
    expect(fixed).toHaveValue(72);
    fireEvent.change(fixed, { target: { value: "48" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(update.mutate.mock.calls.at(-1)?.[0].data.fixed_value).toBe("48");
  });

  it("adds a condition with a fixed value", () => {
    render(<DesignTab protocol={protocol} protocolId="p1" />);
    const header = screen.getByText("Condition Definitions").parentElement?.parentElement;
    fireEvent.click(within(header as HTMLElement).getByRole("button", { name: /Add/ }));
    fireEvent.change(screen.getByPlaceholderText(/Cell Passage/), { target: { value: "Medium" } });
    fireEvent.change(screen.getByLabelText("Fixed for this protocol"), {
      target: { value: "7H9" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(add.mutate.mock.calls[0][0]).toEqual({
      name: "Medium",
      data_type: "text",
      unit: undefined,
      fixed_value: "7H9",
    });
  });
});
