import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const state: { plateMap: unknown } = { plateMap: undefined };

vi.mock("../hooks/use-plate-setup", () => ({ usePlateMap: () => ({ data: state.plateMap }) }));
vi.mock("../hooks/use-dose-response", () => ({ useDoseResponseByRun: () => ({ data: [] }) }));
vi.mock("@/features/attachment", () => ({
  AttachmentList: () => null,
  FileUploadZone: () => null,
}));
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => true }));
vi.mock("./edit-qc-metrics-dialog", () => ({ EditQcMetricsDialog: () => null }));
vi.mock("./grid-import-dialog", () => ({ GridImportDialog: () => null }));
vi.mock("./plate-heatmap", () => ({ PlateHeatmap: () => null }));
vi.mock("./plate-map-viewer", () => ({ PlateMapViewer: () => null }));
vi.mock("./readout-data-table", () => ({ ReadoutDataTable: () => null }));
vi.mock("./run-dr-results", () => ({ RunDoseResponseResults: () => null }));
vi.mock("./run-heatmap-panel", () => ({ RunHeatmapPanel: () => null }));
vi.mock("./run-import-wizard", () => ({ RunImportWizard: () => null }));
vi.mock("./run-plate-link", () => ({ RunPlateLink: () => null }));
vi.mock("./summary-import-wizard", () => ({ SummaryImportWizard: () => null }));

import type { Run } from "../types";
import { RunDataPanel } from "./run-data-panel";

const run = { id: "r1", protocol_id: "p1", is_locked: false, qc_metrics: null } as unknown as Run;

function plateMap(kind: string, curves: boolean) {
  return {
    dose_unit: "uM",
    has_measured_curves: curves,
    plates: [{ plate_id: "pl1", plate_number: 1, holder_kind: kind, wells: [] }],
  };
}

afterEach(() => {
  window.location.hash = "";
});

describe("RunDataPanel holder awareness", () => {
  it("hides Plate Map and Heat Map and shows Curves for a cassette run with curves", () => {
    state.plateMap = plateMap("cassette", true);
    render(<RunDataPanel run={run} />);
    expect(screen.queryByRole("tab", { name: "Plate Map" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "Heat Map" })).toBeNull();
    expect(screen.getByRole("tab", { name: "Curves" })).toBeInTheDocument();
  });

  it("keeps today's tabs and no Curves tab for a plate run without curves", () => {
    state.plateMap = plateMap("plate", false);
    render(<RunDataPanel run={run} />);
    expect(screen.getByRole("tab", { name: "Plate Map" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Heat Map" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Curves" })).toBeNull();
  });

  it("falls back to Readout Data when the hash names a hidden tab", () => {
    window.location.hash = "#plate-map";
    state.plateMap = plateMap("cassette", true);
    render(<RunDataPanel run={run} />);
    expect(screen.getByRole("tab", { name: "Readout Data" })).toHaveAttribute(
      "data-state",
      "active",
    );
  });
});
