import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const state: { plateMap: unknown } = { plateMap: undefined };

vi.mock("../hooks/use-plate-setup", () => ({
  usePlateMap: () => ({ data: state.plateMap, isLoading: state.plateMap === undefined }),
}));
vi.mock("../hooks/use-dose-response", () => ({ useDoseResponseByRun: () => ({ data: [] }) }));
vi.mock("@/features/attachment", () => ({
  AttachmentList: () => null,
  FileUploadZone: () => null,
}));
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => true }));
vi.mock("./edit-qc-metrics-dialog", () => ({ EditQcMetricsDialog: () => null }));
vi.mock("./grid-import-dialog", () => ({ GridImportDialog: () => null }));
vi.mock("./instrument-import-wizard", () => ({ InstrumentImportWizard: () => null }));
vi.mock("./plate-heatmap", () => ({ PlateHeatmap: () => null }));
vi.mock("./plate-map-viewer", () => ({ PlateMapViewer: () => null }));
vi.mock("./readout-data-table", () => ({
  ReadoutDataTable: ({ toolbarActions }: { toolbarActions: React.ReactNode }) => (
    <div>{toolbarActions}</div>
  ),
}));
vi.mock("./run-curves-panel", () => ({ RunCurvesPanel: () => null }));
vi.mock("./run-dr-results", () => ({ RunDoseResponseResults: () => null }));
vi.mock("./run-heatmap-panel", () => ({ RunHeatmapPanel: () => null }));
vi.mock("./run-import-wizard", () => ({ RunImportWizard: () => null }));
vi.mock("./run-plate-link", () => ({ RunPlateLink: () => null }));
vi.mock("./summary-import-wizard", () => ({ SummaryImportWizard: () => null }));

import type { Run } from "../types";
import { RunDataPanel } from "./run-data-panel";

const run = {
  id: "r1",
  protocol_id: "p1",
  is_locked: false,
  status: "in_progress",
  qc_metrics: null,
} as unknown as Run;

const NOT_A_PLATE = "This run's holder is not a plate, so plate imports are not available for it.";

function openImportMenu() {
  fireEvent.keyDown(screen.getByRole("button", { name: /^import$/i }), { key: "Enter" });
}

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
    expect(screen.getByRole("tab", { name: "Traces" })).toBeInTheDocument();
  });

  it("keeps today's tabs and no Curves tab for a plate run without curves", () => {
    state.plateMap = plateMap("plate", false);
    render(<RunDataPanel run={run} />);
    expect(screen.getByRole("tab", { name: "Plate Map" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Heat Map" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Traces" })).toBeNull();
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

  it("opens Curves from #curves once the plate map arrives", () => {
    window.location.hash = "#curves";
    state.plateMap = undefined;
    const { rerender } = render(<RunDataPanel run={run} />);
    // While the plate map loads, the panel does not fall back to Readout Data.
    expect(screen.getByRole("tab", { name: "Readout Data" })).toHaveAttribute(
      "data-state",
      "inactive",
    );
    state.plateMap = plateMap("cassette", true);
    rerender(<RunDataPanel run={run} />);
    expect(screen.getByRole("tab", { name: "Traces" })).toHaveAttribute("data-state", "active");
    expect(window.location.hash).toBe("#curves");
  });

  it("still falls back to Readout Data for a hidden tab once the plate map has loaded", () => {
    window.location.hash = "#plate-map";
    state.plateMap = undefined;
    const { rerender } = render(<RunDataPanel run={run} />);
    state.plateMap = plateMap("cassette", true);
    rerender(<RunDataPanel run={run} />);
    expect(screen.getByRole("tab", { name: "Readout Data" })).toHaveAttribute(
      "data-state",
      "active",
    );
  });

  it("disables the plate-shaped imports, saying why, on a run whose holder is not a plate", () => {
    state.plateMap = plateMap("cassette", true);
    render(<RunDataPanel run={run} />);
    const grid = screen.getByRole("button", { name: /import grid/i });
    expect(grid).toBeDisabled();
    expect(grid.parentElement).toHaveAttribute("title", NOT_A_PLATE);
    openImportMenu();
    const runFile = screen.getByRole("menuitem", { name: /import run file/i });
    expect(runFile).toHaveAttribute("data-disabled");
    expect(runFile).toHaveAttribute("title", NOT_A_PLATE);
  });

  it("keeps the plate-shaped imports for a plate run", () => {
    state.plateMap = plateMap("plate", false);
    render(<RunDataPanel run={run} />);
    expect(screen.getByRole("button", { name: /import grid/i })).toBeEnabled();
    openImportMenu();
    const runFile = screen.getByRole("menuitem", { name: /import run file/i });
    expect(runFile).not.toHaveAttribute("data-disabled");
    expect(runFile).not.toHaveAttribute("title");
  });

  it("says why the instrument file entry is disabled", () => {
    state.plateMap = plateMap("plate", false);
    render(<RunDataPanel run={{ ...run, is_locked: false, status: "completed" } as Run} />);
    openImportMenu();
    const entry = screen.getByRole("menuitem", { name: "Import Instrument File" });
    expect(entry).toHaveAttribute("data-disabled");
    expect(entry).toHaveAttribute(
      "title",
      "Only draft or in-progress runs accept an instrument file.",
    );
  });
});
