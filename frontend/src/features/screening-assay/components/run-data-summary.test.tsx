import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../hooks/use-plate-setup", () => ({
  usePlateMap: () => ({
    data: {
      dose_unit: "uM",
      plates: [
        { plate_id: "pl1", plate_number: 1 },
        { plate_id: "pl2", plate_number: 2 },
      ],
    },
  }),
}));
vi.mock("../hooks/use-protocol-stats", () => ({
  useProtocolPlateQcAverages: () => ({
    data: {
      averages: [
        {
          readout_definition_id: "rd1",
          layer: "percent_inhibition",
          z_prime: { mean: 0.91, sd: 0.007, n: 2 },
          pos_mean: { mean: 100, sd: 0, n: 2 },
          neg_mean: { mean: 0, sd: 3.8, n: 116 },
          control_fits: [
            { role: "positive_control", label: "IC50", value: { mean: 0.45, sd: 0.3, n: 2 } },
          ],
        },
      ],
    },
  }),
}));

import type { Protocol, Run } from "../types";
import { RunDataSummary } from "./run-data-summary";

const layer = (z: number | null, pos: number, neg: number, extra = {}) => ({
  z_prime: z,
  pos_mean: pos,
  pos_sd: 0.451,
  pos_n: 16,
  neg_mean: neg,
  neg_sd: 2.39,
  neg_n: 16,
  ...extra,
});

const run = {
  id: "r1",
  protocol_id: "p1",
  qc_metrics: {
    z_prime: { pl1: { z_prime: 0.915 } },
    plates: {
      pl1: {
        rd1: {
          raw: layer(0.915, 0.067, 0.645),
          percent_inhibition: layer(0.915, 100.00000000000001, 4.8e-15),
        },
      },
      pl2: {
        rd1: {
          percent_inhibition: layer(null, 100, -2, {
            control_fits: [
              {
                role: "positive_control",
                molecule_id: "m",
                label: "IC50",
                value: 0.62,
                curve_class: "full",
              },
            ],
          }),
        },
      },
    },
  },
} as unknown as Run;

const protocol = {
  id: "p1",
  readout_definitions: [{ id: "rd1", name: "Signal", unit: "AU", display_order: 0 }],
} as unknown as Protocol;

const rowOf = (name: string) => screen.getByRole("row", { name: new RegExp(`^${name}`) });

describe("RunDataSummary", () => {
  it("shows each plate's QC per readout layer and the protocol averages", () => {
    render(<RunDataSummary run={run} protocol={protocol} />);

    expect(screen.getByRole("heading", { name: "Data summary" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Signal (AU)" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Signal · % Inhibition" })).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader", { name: "Positive control IC50" })).toHaveLength(1);

    const plate1 = within(rowOf("Plate 1"));
    expect(plate1.getAllByText("0.92")).toHaveLength(2); // raw and % layers
    expect(plate1.getByText("0.067 ± 0.451 (16)")).toBeInTheDocument();
    expect(plate1.getByText("100 ± 0.451 (16)")).toBeInTheDocument();
    expect(plate1.getByText("0 ± 2.39 (16)")).toBeInTheDocument();

    const plate2 = within(rowOf("Plate 2"));
    expect(plate2.getByText("0.62 uM")).toBeInTheDocument();

    const averages = within(rowOf("Protocol averages"));
    expect(averages.getByText("all runs except rejected")).toBeInTheDocument();
    expect(averages.getByText("0.91 ± 0.01 (2 plates)")).toBeInTheDocument();
    expect(averages.getByText("0 ± 3.8 (116 plates)")).toBeInTheDocument();
    expect(averages.getByText("0.45 ± 0.3 uM (2 plates)")).toBeInTheDocument();
  });

  it("renders nothing for a run without per-readout plate QC", () => {
    const legacy = { ...run, qc_metrics: { z_prime: { pl1: { z_prime: 0.9 } } } } as Run;
    const { container } = render(<RunDataSummary run={legacy} protocol={protocol} />);
    expect(container).toBeEmptyDOMElement();
  });
});
