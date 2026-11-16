import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const state: { signal: "high" | "low"; rows: unknown[] } = { signal: "high", rows: [] };

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
          normalizations: ["percent_inhibition"],
        },
      ],
    },
  }),
}));
vi.mock("../hooks/use-dose-response", () => ({ useDoseResponseByRun: () => ({ data: [] }) }));
vi.mock("./run-plate-link", () => ({ RunPlateLink: () => null }));
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

// A1/A2 positive, A3/A4 negative controls; A5–A6 samples.
const PLATE_MAP = {
  dose_unit: "uM",
  plates: [
    {
      plate_id: "pl1",
      plate_number: 1,
      format: "96",
      holder_kind: "plate",
      summary: { total_wells: 6, sample_wells: 2, control_wells: 4 },
      wells: [
        well("A1", "positive_control"),
        well("A2", "positive_control"),
        well("A3", "negative_control"),
        well("A4", "negative_control"),
        well("A5", "sample"),
        well("A6", "sample"),
      ],
    },
  ],
};

const rows = (computed: boolean, values: Record<string, number>) =>
  Object.entries(values).map(([well_id, value_numeric]) => ({
    readout_definition_id: "rd1",
    well_id,
    value_numeric,
    is_computed: computed,
  }));

const run = { id: "r1", protocol_id: "p1", qc_metrics: null } as unknown as Run;

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
