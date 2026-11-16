import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const state: {
  signal: "high" | "low";
  rows: unknown[];
  canEdit: boolean;
  normalizations: string[];
} = {
  signal: "high",
  rows: [],
  canEdit: true,
  normalizations: ["percent_inhibition"],
};
const flag = vi.fn();

vi.mock("../hooks/use-plate-setup", () => ({
  usePlateMap: () => ({ data: PLATE_MAP, isLoading: false }),
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
vi.mock("../hooks/use-dose-response", () => ({ useDoseResponseByRun: () => ({ data: [] }) }));
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
  state.normalizations = ["percent_inhibition"];
  flag.mockReset();
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
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "bubble" } });
    fireEvent.click(screen.getByRole("button", { name: "Flag as outlier" }));
    expect(flag).toHaveBeenCalledWith(
      { runId: "r1", well_ids: ["A5"], outlier: true, reason: "bubble" },
      expect.anything(),
    );
  });

  it("a flagged well offers to remove its flag", () => {
    state.signal = "high";
    state.rows = rows(false, raw, ["A4"]);
    render(<RunHeatmapPanel run={run} />);
    fireEvent.click(document.querySelector('[data-position="A4"]') as HTMLElement);
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
  ])("offers no flag on %s", (_, canEdit, fields) => {
    state.canEdit = canEdit;
    state.signal = "high";
    state.rows = rows(false, raw);
    render(<RunHeatmapPanel run={{ ...run, ...fields } as Run} />);
    fireEvent.click(document.querySelector('[data-position="A5"]') as HTMLElement);
    expect(screen.queryByRole("button", { name: "Flag as outlier" })).toBeNull();
  });
});
