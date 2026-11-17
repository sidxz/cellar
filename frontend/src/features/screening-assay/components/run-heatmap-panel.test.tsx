import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state: {
  signal: "high" | "low";
  rows: unknown[];
  canEdit: boolean;
  normalizations: string[];
  plateMap: unknown;
  curves: unknown[];
} = {
  signal: "high",
  rows: [],
  canEdit: true,
  normalizations: ["percent_inhibition"],
  plateMap: undefined,
  curves: [],
};
const flag = vi.fn();

vi.mock("../hooks/use-plate-setup", () => ({
  usePlateMap: () => ({ data: state.plateMap ?? PLATE_MAP, isLoading: false }),
}));
vi.mock("../hooks/use-readout-data", () => ({
  useReadoutDataByRun: () => ({ data: state.rows, isLoading: false }),
}));
vi.mock("../hooks/use-protocols", () => ({
  useProtocol: () => ({
    data: {
      id: "p1",
      pos_control_signal: state.signal,
      readout_definitions: [
        {
          id: "rd1",
          name: "Signal",
          data_type: "numeric",
          unit: "AU",
          display_order: 0,
          is_calculated: false,
          normalizations: state.normalizations,
        },
      ],
    },
  }),
}));
vi.mock("../hooks/use-dose-response", () => ({
  useDoseResponseByRun: () => ({ data: state.curves }),
}));
vi.mock("./dose-response-figure", () => ({
  DoseResponseChartView: ({ curves }: { curves: { id: string }[] }) => (
    <div>Related curves: {curves.map((curve) => curve.id).join(",")}</div>
  ),
}));
vi.mock("./run-plate-link", () => ({ RunPlateLink: () => null }));
vi.mock("../hooks/use-flag-outliers", () => ({
  useFlagOutliers: () => ({ mutate: flag, isPending: false }),
}));
vi.mock("@/shared/hooks/use-current-user", () => ({ useCanEdit: () => state.canEdit }));
vi.mock("@/shared/lib/toast", () => ({
  showError: vi.fn(),
  showSuccess: vi.fn(),
  showWarning: vi.fn(),
}));
vi.mock("@/shared/components/chemistry", () => ({ StructureThumbnail: () => null }));

import type { Run } from "../types";
import { RunHeatmapPanel } from "./run-heatmap-panel";

const WHITE = "rgb(248, 250, 252)";
const RED = "rgb(220, 38, 38)";

const well = (position: string, well_type: string) => ({
  well_id: position,
  position,
  position_label: position,
  row: position[0],
  column: Number(position.slice(1)),
  well_type,
  registration_number: null,
  label: null,
  note: null,
});

// A1/A2 positive, A3/A4 negative controls; A5–A6 samples; A7 a sample without a value.
const PLATE_MAP = {
  dose_unit: "uM",
  plates: [
    {
      plate_id: "pl1",
      plate_number: 1,
      format: "96",
      holder_kind: "plate",
      summary: { total_wells: 7, sample_wells: 3, control_wells: 4 },
      wells: [
        well("A1", "positive_control"),
        well("A2", "positive_control"),
        well("A3", "negative_control"),
        well("A4", "negative_control"),
        well("A5", "sample"),
        well("A6", "sample"),
        well("A7", "sample"),
      ],
    },
  ],
};

const rows = (computed: boolean, values: Record<string, number>, outliers: string[] = []) =>
  Object.entries(values).map(([well_id, value_numeric]) => ({
    readout_definition_id: "rd1",
    well_id,
    value_numeric,
    is_computed: computed,
    is_outlier: outliers.includes(well_id),
  }));

const run = {
  id: "r1",
  protocol_id: "p1",
  qc_metrics: null,
  status: "draft",
  is_locked: false,
} as unknown as Run;

beforeEach(() => {
  state.canEdit = true;
  state.signal = "high";
  state.rows = [];
  state.normalizations = ["percent_inhibition"];
  state.plateMap = undefined;
  state.curves = [];
  Element.prototype.scrollIntoView = vi.fn();
  flag.mockReset();
});

function multiPlateMap() {
  const sample = (number: number, position: string, molecule: string, dose: number) => ({
    ...well(position, "sample"),
    well_id: `${number}-${position}`,
    molecule_id: molecule,
    registration_number: `CC-${molecule}`,
    batch_id: `batch-${molecule}`,
    batch_number: `CC-${molecule}-001`,
    dose,
  });
  return {
    dose_unit: "uM",
    plates: [
      {
        ...PLATE_MAP.plates[0],
        plate_id: "pl1",
        plate_number: 1,
        summary: { total_wells: 3, sample_wells: 3, control_wells: 0, compounds: 2 },
        wells: [sample(1, "A1", "c1", 1), sample(1, "A2", "c2", 10), sample(1, "A3", "c1", 1)],
      },
      {
        ...PLATE_MAP.plates[0],
        plate_id: "pl2",
        plate_number: 2,
        summary: { total_wells: 3, sample_wells: 3, control_wells: 0, compounds: 2 },
        wells: [sample(2, "A1", "c3", 100), sample(2, "A2", "c1", 1), sample(2, "A3", "c3", 10)],
      },
    ],
  };
}

function selectOption(name: string, option: string) {
  fireEvent.keyDown(screen.getByRole("combobox", { name }), { key: "Enter" });
  fireEvent.click(screen.getByRole("option", { name: option }));
}

function openWellMenu(position: string) {
  fireEvent.contextMenu(document.querySelector(`[data-position="${position}"]`) as HTMLElement, {
    clientX: 80,
    clientY: 80,
  });
}

async function openWellSubmenu(name: string) {
  fireEvent.keyDown(screen.getByRole("menuitem", { name }), { key: "ArrowRight" });
  return screen.findByRole("menu", { name });
}

describe("well context menu", () => {
  beforeEach(() => {
    state.rows = rows(false, { A1: 1, A4: 2, A5: 0.3 });
  });

  it("excludes only the targeted well using the selected reason", async () => {
    render(<RunHeatmapPanel run={run} />);
    openWellMenu("A5");
    expect(flag).not.toHaveBeenCalled();
    await openWellSubmenu("Exclude from QC");
    fireEvent.click(screen.getByRole("menuitem", { name: "Dispensing failure" }));
    expect(flag).toHaveBeenCalledWith(
      { runId: "r1", well_ids: ["A5"], outlier: true, reason: "Dispensing failure" },
      expect.anything(),
    );
  });

  it("restores an excluded control with an explicit reason on a completed run", async () => {
    state.rows = rows(false, { A4: 2 }, ["A4"]);
    render(<RunHeatmapPanel run={{ ...run, status: "completed" }} />);
    openWellMenu("A4");
    await openWellSubmenu("Restore to QC");
    fireEvent.click(screen.getByRole("menuitem", { name: "Exclusion applied in error" }));
    expect(flag).toHaveBeenCalledWith(
      { runId: "r1", well_ids: ["A4"], outlier: false, reason: "Exclusion applied in error" },
      expect.anything(),
    );
  });

  it("supports a custom reason without changing data until submitted", async () => {
    render(<RunHeatmapPanel run={run} />);
    openWellMenu("A5");
    await openWellSubmenu("Exclude from QC");
    fireEvent.click(screen.getByRole("menuitem", { name: "Other reason…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Exclude well" })).toBeDisabled();
    expect(flag).not.toHaveBeenCalled();
    fireEvent.change(within(dialog).getByLabelText("Reason"), {
      target: { value: "Plate reader artefact" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Exclude well" }));
    expect(flag).toHaveBeenCalledWith(
      { runId: "r1", well_ids: ["A5"], outlier: true, reason: "Plate reader artefact" },
      expect.anything(),
    );
  });

  it.each([
    ["a viewer", false, { status: "draft", is_locked: false }],
    ["an approved run", true, { status: "approved", is_locked: false }],
    ["a locked run", true, { status: "completed", is_locked: true }],
    ["a rejected run", true, { status: "rejected", is_locked: false }],
  ])("keeps inspection available but excludes no wells for %s", (_, canEdit, fields) => {
    state.canEdit = canEdit;
    render(<RunHeatmapPanel run={{ ...run, ...fields } as Run} />);
    openWellMenu("A5");
    expect(screen.getByRole("menuitem", { name: "Exclude from QC" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(
      screen.getByRole("menuitem", { name: "Inspect well and replicates" }),
    ).not.toHaveAttribute("aria-disabled", "true");
    expect(flag).not.toHaveBeenCalled();
  });

  it("does not offer exclusion for a well without raw values", () => {
    render(<RunHeatmapPanel run={run} />);
    openWellMenu("A7");
    expect(screen.getByRole("menuitem", { name: "Exclude from QC" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByText("No raw measurement to exclude.")).toBeInTheDocument();
  });

  it("opens well details from the context menu", () => {
    render(<RunHeatmapPanel run={run} />);
    openWellMenu("A5");
    fireEvent.click(screen.getByRole("menuitem", { name: "Inspect well and replicates" }));
    expect(screen.getByRole("dialog", { name: "Plate 1 · A5" })).toBeInTheDocument();
  });

  it("ties the tooltip to one well, its plate and its row/column labels", async () => {
    render(<RunHeatmapPanel run={run} />);
    const a5 = document.querySelector('[data-position="A5"]') as HTMLElement;
    const colour = a5.style.background;
    fireEvent.focus(a5);
    const tooltip = await screen.findByRole("tooltip");
    expect(within(tooltip).getByText("Plate 1")).toBeInTheDocument();
    expect(within(tooltip).getByText("A5")).toBeInTheDocument();
    expect(a5).toHaveAttribute("aria-describedby", tooltip.id);
    expect(a5).toHaveAttribute("data-hovered", "true");
    expect(
      [...document.querySelectorAll('[data-active="true"]')].map((element) => element.textContent),
    ).toEqual(["5", "A"]);
    expect(a5.style.background).toBe(colour);
    fireEvent.click(a5);
    expect(screen.getByRole("dialog", { name: "Plate 1 · A5" })).toBeInTheDocument();
    expect(a5).toHaveAttribute("aria-pressed", "true");
    expect(a5).not.toHaveAttribute("data-hovered");
  });

  it("lets the pointer scan right to the next well and inspect that well", async () => {
    render(<RunHeatmapPanel run={run} />);
    const a5 = document.querySelector('[data-position="A5"]') as HTMLElement;
    const a6 = document.querySelector('[data-position="A6"]') as HTMLElement;
    fireEvent.pointerMove(a5, { pointerType: "mouse", clientX: 80, clientY: 80 });
    expect(within(await screen.findByRole("tooltip")).getByText("A5")).toBeInTheDocument();
    fireEvent.pointerLeave(a5, { pointerType: "mouse", clientX: 100, clientY: 80 });
    fireEvent.pointerMove(a6, { pointerType: "mouse", clientX: 110, clientY: 80 });
    await waitFor(() =>
      expect(within(screen.getByRole("tooltip")).getByText("A6")).toBeInTheDocument(),
    );
    expect(a5).not.toHaveAttribute("data-hovered");
    expect(a6).toHaveAttribute("data-hovered", "true");
    fireEvent.click(a6);
    expect(screen.getByRole("dialog", { name: "Plate 1 · A6" })).toBeInTheDocument();
    expect(flag).not.toHaveBeenCalled();
  });

  it("highlights replicate wells across plates while preserving response colours", () => {
    state.plateMap = multiPlateMap();
    state.normalizations = [];
    state.rows = rows(false, { "1-A1": 0.3, "1-A2": 1, "1-A3": 0.4, "2-A2": 0.2 });
    render(<RunHeatmapPanel run={run} />);
    const cell = screen
      .getByRole("article", { name: "Plate 1" })
      .querySelector('[data-position="A1"]') as HTMLElement;
    const colour = cell.style.background;
    fireEvent.contextMenu(cell, { clientX: 80, clientY: 80 });
    fireEvent.click(screen.getByRole("menuitem", { name: "Highlight replicates (3)" }));
    expect(document.querySelectorAll('[data-highlighted="true"]')).toHaveLength(3);
    expect(cell.style.background).toBe(colour);
    expect(flag).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Clear highlights" }));
    expect(document.querySelectorAll('[data-highlighted="true"]')).toHaveLength(0);
  });

  it("copies full-precision values with plate, well and units for spreadsheets", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    state.rows = rows(false, { A5: 0.314159265 });
    render(<RunHeatmapPanel run={run} />);
    openWellMenu("A5");
    await openWellSubmenu("Copy");
    fireEvent.click(screen.getByRole("menuitem", { name: "Well values (spreadsheet)" }));
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("0.314159265"));
    const text = writeText.mock.calls[0][0] as string;
    expect(text).toContain("Concentration (uM)");
    expect(text).toContain("Signal · Raw (AU)");
    expect(text).toContain("1\tA5\t");
  });
});

describe("all-plate overview", () => {
  beforeEach(() => {
    state.plateMap = multiPlateMap();
    state.normalizations = [];
    state.rows = rows(false, { "1-A1": 0, "1-A2": 10, "1-A3": 20, "2-A1": 10, "2-A2": 100 });
  });

  const cell = (plateName: string, position: string) =>
    screen
      .getByRole("article", { name: plateName })
      .querySelector(`[data-position="${position}"]`) as HTMLElement;

  it("shows both plates, comparable response colours, and coverage without a plate selector", () => {
    render(<RunHeatmapPanel run={run} />);
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(screen.queryByRole("combobox", { name: "Plate" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Colour by" })).toHaveTextContent("Response");
    expect(cell("Plate 1", "A2").style.background).toBe(cell("Plate 2", "A1").style.background);
    expect(
      within(screen.getByRole("article", { name: "Plate 2" })).getByText("1 without a value"),
    ).toBeVisible();
    expect(document.querySelectorAll("details[open]")).toHaveLength(0);
  });

  it("makes per-plate autoscaling explicit and leaves the shared scale as the default", () => {
    render(<RunHeatmapPanel run={run} />);
    const sharedColor = cell("Plate 1", "A2").style.background;
    selectOption("Scale range", "Per plate");
    expect(screen.getByText(/colours are not directly comparable/)).toBeVisible();
    expect(cell("Plate 1", "A2").style.background).not.toBe(sharedColor);
    expect(cell("Plate 1", "A2").style.background).not.toBe(cell("Plate 2", "A1").style.background);
    selectOption("Scale range", "Shared across plates");
    expect(cell("Plate 1", "A2").style.background).toBe(sharedColor);
  });

  it("keeps compound identity and concentration colouring consistent across plates", () => {
    render(<RunHeatmapPanel run={run} />);
    selectOption("Colour by", "Compound");
    expect(cell("Plate 1", "A1").style.background).toBe(cell("Plate 2", "A2").style.background);
    expect(cell("Plate 1", "A1").style.background).not.toBe(cell("Plate 1", "A2").style.background);
    selectOption("Colour by", "Concentration");
    expect(cell("Plate 1", "A1").style.background).toBe(cell("Plate 2", "A2").style.background);
    expect(
      within(screen.getByRole("region", { name: "Shared colour scale" })).getByText(
        "Concentration (uM)",
      ),
    ).toBeVisible();
    selectOption("Colour by", "Well type");
    expect(cell("Plate 1", "A1").style.background).toBe(cell("Plate 2", "A1").style.background);
  });

  it("opens well values, the correct batch's curves, and matching replicate wells", () => {
    state.curves = [
      { id: "matching-fit", molecule_id: "c1", batch_id: "batch-c1" },
      { id: "other-batch-fit", molecule_id: "c1", batch_id: "different-batch" },
    ];
    render(<RunHeatmapPanel run={run} />);
    fireEvent.click(cell("Plate 1", "A1"));
    const details = screen.getByRole("dialog", { name: "Plate 1 · A1" });
    expect(within(details).getByRole("link", { name: "CC-c1" })).toHaveAttribute(
      "href",
      "/compounds/c1",
    );
    expect(within(details).getByText("1 uM")).toBeVisible();
    expect(within(details).getByText(/3 wells/)).toBeVisible();
    expect(within(details).getByText("Related curves: matching-fit")).toBeVisible();
    expect(within(details).queryByText(/other-batch-fit/)).not.toBeInTheDocument();
    expect(flag).not.toHaveBeenCalled();
  });

  it("uses compact previews for large runs and expands a plate for well inspection", () => {
    const base = multiPlateMap().plates[0];
    state.plateMap = {
      dose_unit: "uM",
      plates: Array.from({ length: 7 }, (_, index) => ({
        ...base,
        plate_id: `pl${index + 1}`,
        plate_number: index + 1,
        wells: base.wells.map((well) => ({ ...well, well_id: `${index + 1}-${well.position}` })),
      })),
    };
    render(<RunHeatmapPanel run={run} />);
    expect(screen.getAllByRole("img", { name: /Plate \d+ preview/ })).toHaveLength(7);
    fireEvent.click(screen.getByRole("button", { name: "Expand Plate 2" }));
    const expanded = screen.getByRole("dialog", { name: "Plate 2" });
    const wellButton = within(expanded).getByRole("button", { name: "A1" });
    expect(wellButton).toBeVisible();
    fireEvent.click(wellButton);
    const details = screen.getByRole("dialog", { name: "Plate 2 · A1" });
    expect(within(details).getByRole("link", { name: "CC-c1" })).toBeVisible();
    fireEvent.click(within(details).getByRole("button", { name: "Close" }));
    expect(screen.getByRole("dialog", { name: "Plate 2" })).toBeVisible();
  });

  it("does not assign another batch's curves or replicate wells to an unbatched sample", () => {
    const map = multiPlateMap();
    state.plateMap = {
      ...map,
      plates: [
        {
          ...map.plates[0],
          wells: [
            { ...map.plates[0].wells[0], batch_id: null, batch_number: null },
            ...map.plates[0].wells.slice(1),
          ],
        },
        map.plates[1],
      ],
    };
    state.curves = [{ id: "different-sample", molecule_id: "c1", batch_id: "batch-c1" }];
    render(<RunHeatmapPanel run={run} />);
    fireEvent.click(cell("Plate 1", "A1"));
    const details = screen.getByRole("dialog", { name: "Plate 1 · A1" });
    expect(within(details).queryByText(/Related curves/)).not.toBeInTheDocument();
    expect(within(details).queryByText(/wells/)).not.toBeInTheDocument();
  });
});

it("shows QC for the selected readout and value layer before overall QC", () => {
  state.rows = [
    ...rows(false, { A1: 1, A3: 0.1, A5: 0.1, A6: 1 }, ["A3"]),
    ...rows(true, { A1: 0, A3: 100, A5: 100, A6: 0 }),
  ];
  const withQc = {
    ...run,
    qc_metrics: {
      z_prime: { pl1: { z_prime: 0.2 } },
      plates: {
        pl1: { rd1: { percent_inhibition: { z_prime: 0.91, s2b: 8 }, raw: { z_prime: 0.73 } } },
      },
    },
  } as Run;
  render(<RunHeatmapPanel run={withQc} />);
  const card = screen.getByRole("article", { name: "Plate 1" });
  expect(within(card).getByText("0.91")).toBeVisible();
  expect(within(card).getByText("1 excluded")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Raw" }));
  expect(within(card).getByText("0.73")).toBeVisible();
});

function colorOf(position: string) {
  return (document.querySelector(`[data-position="${position}"]`) as HTMLElement).style.background;
}

describe("RunHeatmapPanel scale", () => {
  // Raw signal: the uninhibited control reads 1.0, the inhibited one 0.1. Under HIGH the
  // positive control is the uninhibited one; under LOW it is the known inhibitor.
  const raw = {
    high: { A1: 1.0, A2: 1.0, A3: 0.1, A4: 0.1, A5: 0.1, A6: 1.0 },
    low: { A1: 0.1, A2: 0.1, A3: 1.0, A4: 1.0, A5: 0.1, A6: 1.0 },
  };
  const pct = (signal: "high" | "low") =>
    Object.fromEntries(Object.entries(raw[signal]).map(([w, v]) => [w, (100 * (1.0 - v)) / 0.9]));

  it.each(["high", "low"] as const)(
    "percent inhibition: none white, full red, controls filled (%s convention)",
    (signal) => {
      state.signal = signal;
      state.rows = [...rows(false, raw[signal]), ...rows(true, pct(signal))];
      render(<RunHeatmapPanel run={run} />);
      expect(colorOf("A5")).toBe(RED); // full inhibition
      expect(colorOf("A6")).toBe(WHITE); // inactive
      const inhibitor = signal === "high" ? "A3" : "A1";
      const uninhibited = signal === "high" ? "A1" : "A3";
      expect(colorOf(inhibitor)).toBe(RED);
      expect(colorOf(uninhibited)).toBe(WHITE);
      expect(screen.getByText("0 %")).toBeInTheDocument();
      expect(screen.getByText("100 %")).toBeInTheDocument();
    },
  );

  it.each(["high", "low"] as const)(
    "raw: the uninhibited control's mean is white, the inhibited one's red (%s convention)",
    (signal) => {
      state.signal = signal;
      state.rows = [...rows(false, raw[signal]), ...rows(true, pct(signal))];
      render(<RunHeatmapPanel run={run} />);
      fireEvent.click(screen.getByRole("button", { name: "Raw" }));
      expect(colorOf("A5")).toBe(RED);
      expect(colorOf("A6")).toBe(WHITE);
    },
  );
});

describe("RunHeatmapPanel activation", () => {
  // % activation under HIGH: the positive control is the full activator (raw 1.0, the
  // 100 % anchor), the negative control the basal no-effect well (raw 0.1).
  const raw = { A1: 1.0, A2: 1.0, A3: 0.1, A4: 0.1, A5: 1.0, A6: 0.1 };

  it("raw: the no-effect control's mean is white, the full activator's red", () => {
    state.signal = "high";
    state.normalizations = ["percent_activation"];
    state.rows = rows(false, raw);
    render(<RunHeatmapPanel run={run} />);
    fireEvent.click(screen.getByRole("button", { name: "Raw" }));
    expect(colorOf("A5")).toBe(RED); // active
    expect(colorOf("A6")).toBe(WHITE); // inactive
    expect(screen.getByText("POS 1 AU")).toBeInTheDocument();
    expect(screen.getByText("NEG 0.1 AU")).toBeInTheDocument();
  });
});

describe("RunHeatmapPanel control colours", () => {
  const BLUE = "rgb(37, 99, 235)";
  const borderOf = (position: string) =>
    (document.querySelector(`[data-position="${position}"]`) as HTMLElement).style.border;

  it.each([
    ["high", ["percent_inhibition"], "A3", "A1"],
    ["low", ["percent_inhibition"], "A1", "A3"],
    ["high", ["percent_activation"], "A1", "A3"],
  ] as const)(
    "%s signal, %s: the full-effect control is outlined red, the no-effect one blue",
    (signal, normalizations, full, none) => {
      state.signal = signal;
      state.normalizations = [...normalizations];
      state.rows = [];
      render(<RunHeatmapPanel run={run} />);
      expect(borderOf(full)).toContain(RED);
      expect(borderOf(none)).toContain(BLUE);
    },
  );
});

describe("RunHeatmapPanel outliers and empty wells", () => {
  const GREY = "rgb(203, 213, 225)";
  // HIGH: POS (uninhibited) 1.0 is white, NEG 0.1 red; A4 reads wild and is flagged.
  const raw = { A1: 1.0, A2: 1.0, A3: 0.1, A4: 9.0, A5: 0.1, A6: 1.0 };

  it("draws a well without a value, and a position without a well, light grey", () => {
    state.signal = "high";
    state.rows = rows(false, raw);
    render(<RunHeatmapPanel run={run} />);
    expect(colorOf("A7")).toBe(GREY);
    expect(colorOf("A12")).toBe(GREY);
  });

  it("marks a flagged well with an X and leaves it out of the raw anchors", () => {
    state.signal = "high";
    state.rows = rows(false, raw, ["A4"]);
    render(<RunHeatmapPanel run={run} />);
    fireEvent.click(screen.getByRole("button", { name: "Raw" }));
    const a4 = document.querySelector('[data-position="A4"]') as HTMLElement;
    expect(within(a4).getByLabelText("Outlier")).toBeInTheDocument();
    expect(document.querySelector('[data-position="A3"] [aria-label="Outlier"]')).toBeNull();
    // NEG mean is A3 alone (0.1): with A4 in it, A5 (0.1) would no longer be red.
    expect(colorOf("A5")).toBe(RED);
    expect(colorOf("A6")).toBe(WHITE);
  });

  it("an editor clicks a well and flags it with a reason", () => {
    state.signal = "high";
    state.rows = rows(false, raw);
    render(<RunHeatmapPanel run={run} />);
    fireEvent.click(document.querySelector('[data-position="A5"]') as HTMLElement);
    fireEvent.click(screen.getByRole("button", { name: "Outlier options" }));
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "bubble" } });
    fireEvent.click(screen.getByRole("button", { name: "Flag as outlier" }));
    expect(flag).toHaveBeenCalledWith(
      { runId: "r1", well_ids: ["A5"], outlier: true, reason: "bubble" },
      expect.anything(),
    );
  });

  it("asks for a reason on a completed run", () => {
    state.signal = "high";
    state.rows = rows(false, raw);
    render(<RunHeatmapPanel run={{ ...run, status: "completed" } as Run} />);
    fireEvent.click(document.querySelector('[data-position="A5"]') as HTMLElement);
    fireEvent.click(screen.getByRole("button", { name: "Outlier options" }));
    expect(screen.getByRole("button", { name: "Flag as outlier" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "bubble" } });
    expect(screen.getByRole("button", { name: "Flag as outlier" })).toBeEnabled();
  });

  it("a flagged well offers to remove its flag", () => {
    state.signal = "high";
    state.rows = rows(false, raw, ["A4"]);
    render(<RunHeatmapPanel run={run} />);
    fireEvent.click(document.querySelector('[data-position="A4"]') as HTMLElement);
    fireEvent.click(screen.getByRole("button", { name: "Outlier options" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove outlier flag" }));
    expect(flag).toHaveBeenCalledWith(
      { runId: "r1", well_ids: ["A4"], outlier: false, reason: null },
      expect.anything(),
    );
  });

  it.each([
    ["a viewer", false, { status: "draft", is_locked: false }],
    ["an approved run", true, { status: "approved", is_locked: false }],
    ["a locked run", true, { status: "completed", is_locked: true }],
    ["a rejected run", true, { status: "rejected", is_locked: false }],
  ])("offers no flag on %s", (_, canEdit, fields) => {
    state.canEdit = canEdit;
    state.signal = "high";
    state.rows = rows(false, raw);
    render(<RunHeatmapPanel run={{ ...run, ...fields } as Run} />);
    fireEvent.click(document.querySelector('[data-position="A5"]') as HTMLElement);
    expect(screen.queryByRole("button", { name: "Flag as outlier" })).toBeNull();
  });
});
