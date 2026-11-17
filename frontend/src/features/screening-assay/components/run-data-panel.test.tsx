import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const state: { plateMap: unknown; canEdit: boolean; protocol: unknown } = {
  plateMap: undefined,
  canEdit: true,
  protocol: undefined,
};

vi.mock("../hooks/use-plate-setup", () => ({
  usePlateMap: () => ({ data: state.plateMap, isLoading: state.plateMap === undefined }),
}));
vi.mock("../hooks/use-dose-response", () => ({ useDoseResponseByRun: () => ({ data: [] }) }));
vi.mock("../hooks/use-protocols", () => ({
  useProtocol: () => ({ data: state.protocol, isLoading: state.protocol === undefined }),
}));
vi.mock("@/features/attachment", () => ({
  AttachmentList: () => <div>Run attachments</div>,
  FileUploadZone: () => null,
}));
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => state.canEdit }));
vi.mock("./edit-qc-metrics-dialog", () => ({ EditQcMetricsDialog: () => null }));
vi.mock("./grid-import-dialog", () => ({ GridImportDialog: () => null }));
vi.mock("./instrument-import-wizard", () => ({ InstrumentImportWizard: () => null }));
vi.mock("./plate-heatmap", () => ({ PlateHeatmap: () => null }));
vi.mock("./plate-map-viewer", () => ({
  PlateMapViewer: ({ plate }: { plate: { plate_number: number } }) => (
    <div>Layout for plate {plate.plate_number}</div>
  ),
}));
vi.mock("./readout-data-table", () => ({
  ReadoutDataTable: () => <input aria-label="Filter results" />,
}));
vi.mock("./run-curves-panel", () => ({ RunCurvesPanel: () => <div>Measured traces</div> }));
vi.mock("./run-dr-results", () => ({
  RunDoseResponseResults: () => <div>Dose-response results</div>,
}));
vi.mock("./run-heatmap-panel", () => ({
  RunHeatmapPanel: ({
    colorBy,
    onColorByChange,
  }: { colorBy: string; onColorByChange: (value: string) => void }) => (
    <div>
      <span>All plates: {colorBy}</span>
      <button type="button" onClick={() => onColorByChange("compound")}>
        Colour by compound
      </button>
    </div>
  ),
}));
vi.mock("./run-import-wizard", () => ({ RunImportWizard: () => null }));
vi.mock("./run-plate-link", () => ({ RunPlateLink: () => null }));
vi.mock("./summary-import-wizard", () => ({ SummaryImportWizard: () => null }));
vi.mock("./run-data-summary", () => ({
  RunDataSummary: () => <div>Plate quality summary</div>,
}));
vi.mock("./run-details-panel", () => ({
  RunDetailsPanel: () => <div>Run details</div>,
}));

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

function selectTab(name: string) {
  fireEvent.mouseDown(screen.getByRole("tab", { name }), {
    button: 0,
    ctrlKey: false,
  });
}

function plateMap(kind: string, curves: boolean) {
  return {
    dose_unit: "uM",
    has_measured_curves: curves,
    plates: [{ plate_id: "pl1", plate_number: 1, holder_kind: kind, wells: [] }],
  };
}

beforeEach(() => {
  state.canEdit = true;
  state.protocol = { readout_definitions: [{ data_type: "dose_response" }] };
  state.plateMap = plateMap("plate", false);
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("RunDataPanel navigation", () => {
  it("opens dose-response first without mounting readouts, quality, or metadata", () => {
    render(<RunDataPanel run={run} />);
    expect(screen.getByRole("tablist", { name: "Run sections" })).toHaveTextContent(
      "ResultsPlatesQualityDetailsFiles",
    );
    expect(screen.getByRole("tab", { name: "Results" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tablist", { name: "Result view" })).toHaveTextContent(
      "Dose-responseReadouts",
    );
    expect(screen.getByRole("tab", { name: "Dose-response" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("Dose-response results")).toBeVisible();
    expect(screen.queryByRole("textbox", { name: "Filter results" })).not.toBeInTheDocument();
    expect(screen.queryByText("Plate quality summary")).not.toBeInTheDocument();
    expect(screen.queryByText("Run details")).not.toBeInTheDocument();

    selectTab("Quality");
    expect(screen.getByText("Plate quality summary")).toBeVisible();
    selectTab("Details");
    expect(screen.getByText("Run details")).toBeVisible();
  });

  it("waits for the assay type before choosing its default Results view", () => {
    state.protocol = undefined;
    state.plateMap = undefined;
    const { rerender } = render(<RunDataPanel run={run} />);
    expect(screen.getByText("Loading results…")).toBeVisible();
    expect(screen.queryByRole("textbox", { name: "Filter results" })).not.toBeInTheDocument();
    state.protocol = { readout_definitions: [{ data_type: "dose_response" }] };
    state.plateMap = plateMap("plate", false);
    rerender(<RunDataPanel run={run} />);
    expect(screen.getByRole("tab", { name: "Dose-response" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it.each([
    ["readout", "Results", "Readouts"],
    ["dose-response", "Results", "Dose-response"],
    ["curves", "Results", "Traces"],
    ["plate-map", "Plates", "compound"],
    ["heat-map", "Plates", "response"],
    ["qc", "Quality", null],
  ])("keeps a legacy #%s link working", (hash, section, view) => {
    state.plateMap = plateMap("plate", true);
    window.history.replaceState(null, "", `#${hash}`);
    render(<RunDataPanel run={run} />);
    expect(screen.getByRole("tab", { name: section })).toHaveAttribute("aria-selected", "true");
    if (section === "Plates") expect(screen.getByText(`All plates: ${view}`)).toBeVisible();
    else if (view)
      expect(screen.getByRole("tab", { name: view })).toHaveAttribute("aria-selected", "true");
  });

  it("retains filters and the chosen results view across sections", () => {
    render(<RunDataPanel run={run} />);
    selectTab("Readouts");
    fireEvent.change(screen.getByRole("textbox", { name: "Filter results" }), {
      target: { value: "CC-061341" },
    });
    selectTab("Dose-response");
    selectTab("Quality");
    selectTab("Results");
    expect(screen.getByRole("tab", { name: "Dose-response" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("Dose-response results")).toBeVisible();
    selectTab("Readouts");
    expect(screen.getByRole("textbox", { name: "Filter results" })).toHaveValue("CC-061341");
  });

  it("hides dose-response when the protocol has no dose-response readouts", () => {
    state.protocol = { readout_definitions: [{ data_type: "numeric" }] };
    render(<RunDataPanel run={run} />);
    expect(screen.queryByRole("tab", { name: "Dose-response" })).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Readouts" })).toHaveAttribute("aria-selected", "true");
  });

  it("surfaces poor quality from Results and links to its full details", () => {
    render(<RunDataPanel run={{ ...run, qc_metrics: { z_prime: -0.2 } } as Run} />);
    expect(screen.getByRole("status")).toHaveTextContent("QC needs review");
    fireEvent.click(screen.getByRole("button", { name: "Review quality" }));
    expect(screen.getByRole("tab", { name: "Quality" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Plate quality summary")).toBeVisible();
  });

  it("opens all plates in Response and retains colouring across sections", () => {
    render(<RunDataPanel run={run} />);
    selectTab("Plates");
    expect(screen.getByText("All plates: response")).toBeVisible();
    expect(screen.queryByRole("combobox", { name: "Plate" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Colour by compound" }));
    expect(window.location.hash).toBe("#plate-map");
    selectTab("Quality");
    selectTab("Plates");
    expect(screen.getByText("All plates: compound")).toBeVisible();
  });
});

describe("RunDataPanel holder awareness", () => {
  it("defaults to Traces before Readouts for a cassette run with measured curves", () => {
    state.protocol = { readout_definitions: [{ data_type: "numeric" }] };
    state.plateMap = plateMap("cassette", true);
    render(<RunDataPanel run={run} />);
    expect(screen.queryByRole("tab", { name: "Plates" })).toBeNull();
    expect(screen.getByRole("tab", { name: "Traces" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Traces" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tablist", { name: "Result view" })).toHaveTextContent(
      "TracesReadouts",
    );
  });

  it("keeps Plates and no Traces view for a plate run without curves", () => {
    render(<RunDataPanel run={run} />);
    expect(screen.getByRole("tab", { name: "Plates" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Traces" })).toBeNull();
  });

  it("falls back to the default Results view when the hash names a hidden plate view", () => {
    window.history.replaceState(null, "", "#plate-map");
    state.plateMap = plateMap("cassette", true);
    render(<RunDataPanel run={run} />);
    expect(screen.getByRole("tab", { name: "Dose-response" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("opens Traces from #curves once the plate map arrives", () => {
    window.history.replaceState(null, "", "#curves");
    state.plateMap = undefined;
    const { rerender } = render(<RunDataPanel run={run} />);
    expect(screen.getByText("Loading traces…")).toBeVisible();
    state.plateMap = plateMap("cassette", true);
    rerender(<RunDataPanel run={run} />);
    expect(screen.getByRole("tab", { name: "Traces" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Measured traces")).toBeVisible();
    expect(window.location.hash).toBe("#curves");
  });

  it("falls back for a hidden plate view once the plate map has loaded", () => {
    window.history.replaceState(null, "", "#heat-map");
    state.plateMap = undefined;
    const { rerender } = render(<RunDataPanel run={run} />);
    state.plateMap = plateMap("cassette", true);
    rerender(<RunDataPanel run={run} />);
    expect(screen.getByRole("tab", { name: "Dose-response" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("disables plate imports with a reason on non-plate holders", () => {
    state.plateMap = plateMap("cassette", true);
    render(<RunDataPanel run={run} />);
    openImportMenu();
    for (const name of [/import run file/i, /import grid/i]) {
      const entry = screen.getByRole("menuitem", { name });
      expect(entry).toHaveAttribute("data-disabled");
      expect(entry).toHaveAttribute("title", NOT_A_PLATE);
    }
  });

  it("keeps plate imports inside the Import menu for a plate run", () => {
    render(<RunDataPanel run={run} />);
    expect(screen.queryByRole("button", { name: /import grid/i })).not.toBeInTheDocument();
    openImportMenu();
    const menu = screen.getByRole("menu");
    for (const name of [/import run file/i, /import grid/i]) {
      expect(within(menu).getByRole("menuitem", { name })).not.toHaveAttribute("data-disabled");
    }
  });

  it("says why the instrument file entry is disabled", () => {
    render(<RunDataPanel run={{ ...run, status: "completed" } as Run} />);
    openImportMenu();
    const entry = screen.getByRole("menuitem", { name: "Import Instrument File" });
    expect(entry).toHaveAttribute("data-disabled");
    expect(entry).toHaveAttribute(
      "title",
      "Only draft or in-progress runs accept an instrument file.",
    );
  });

  it("keeps imports disabled on locked runs", () => {
    render(<RunDataPanel run={{ ...run, is_locked: true } as Run} />);
    expect(screen.getByRole("button", { name: /^import$/i })).toBeDisabled();
  });

  it("offers no import or quality editing controls to viewers", () => {
    state.canEdit = false;
    render(<RunDataPanel run={run} />);
    expect(screen.queryByRole("button", { name: /^import$/i })).not.toBeInTheDocument();
    selectTab("Quality");
    expect(screen.queryByRole("button", { name: "Edit Metrics" })).not.toBeInTheDocument();
  });
});
