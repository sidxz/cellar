import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

// Radix Select opens via a listbox portal that calls scrollIntoView +
// hasPointerCapture on its items — jsdom ships neither. Polyfill so the
// open/click flow works under test.
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn();
  }
});
import type { ProtocolSummary } from "@/features/screening-assay/hooks/use-protocols";
import type { Protocol } from "@/features/screening-assay/types";
import type { SarColorSpec } from "../lib/sar-color-spec";
import { RGroupColorControl } from "./rgroup-color-control";

// ─── Mock hooks ───────────────────────────────────────────────────────────────

vi.mock("@/features/screening-assay/hooks/use-protocols", () => ({
  useProtocolSummaries: vi.fn(),
  useProtocol: vi.fn(),
}));

// ─── Fixtures ─────────────────────────────────────────────────────────────────

/** A minimal Protocol fixture with one DR readout-def (IC50 primary intercept). */
const TEST_PROTOCOL: Protocol = {
  id: "proto-1",
  workspace_id: "ws-1",
  name: "EGFR Biochemical",
  description: null,
  protocol_type: "biochemical",
  targets: [],
  category: null,
  protocol_version: 1,
  parent_protocol_id: null,
  status: "active",
  created_by: "user-1",
  dose_unit: "uM",
  pos_control_signal: "high",
  readout_definitions: [
    {
      id: "rd-1",
      name: "IC50",
      description: null,
      data_type: "dose_response",
      unit: "uM",
      aggregation: "none",
      precision: null,
      normalizations: [],
      is_calculated: false,
      calculation_formula: null,
      display_order: 0,
      pick_list_values: null,
      dose_response_config: {
        curve_type: "ic50",
        x_readout_name: null,
        y_readout_name: "raw",
        intercepts: [{ kind: "ic", level: 50, basis: "relative_percent" }],
        hill_slope_constraint: "unconstrained",
        activity_threshold: null,
        normalization_scope: "none",
        top_constraint: null,
        bottom_constraint: null,
        top_constraint_min: null,
        top_constraint_max: null,
        bottom_constraint_min: null,
        bottom_constraint_max: null,
        hill_slope_min: null,
        hill_slope_max: null,
        outlier_sigma: null,
      },
    },
  ],
  condition_definitions: [],
  control_layouts: null,
  ontology_annotations: null,
  project_ids: [],
  recommended_hit_criteria: null,
  is_locked: false,
  locked_by: null,
  lock_reason: null,
  locked_at: null,
};

const TEST_SUMMARY: ProtocolSummary = {
  id: "proto-1",
  name: "EGFR Biochemical",
  status: "active",
  protocol_type: "biochemical",
};

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("RGroupColorControl", () => {
  beforeEach(async () => {
    const { useProtocolSummaries, useProtocol } = await import(
      "@/features/screening-assay/hooks/use-protocols"
    );
    vi.mocked(useProtocolSummaries).mockReturnValue({
      data: [TEST_SUMMARY],
      isLoading: false,
      isError: false,
    } as never);
    // Before a protocol is selected, return empty data
    vi.mocked(useProtocol).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as never);
  });

  it("calls onChange with a SarColorSpec whose column is drc:<rd> on protocol+readout pick", async () => {
    const { useProtocol } = await import("@/features/screening-assay/hooks/use-protocols");

    // After a protocol id is selected, return the full protocol
    vi.mocked(useProtocol).mockReturnValue({
      data: TEST_PROTOCOL,
      isLoading: false,
      isError: false,
    } as never);

    const onChange = vi.fn();

    render(
      <RGroupColorControl
        value={null}
        onChange={onChange}
        aggregationMode="latest"
        onAggregationChange={vi.fn()}
      />,
    );

    // Open protocol picker and select "EGFR Biochemical"
    const protocolTrigger = screen.getByRole("combobox", { name: "Protocol" });
    fireEvent.click(protocolTrigger);
    const protocolOption = screen.getByRole("option", { name: "EGFR Biochemical" });
    fireEvent.click(protocolOption);

    // Now the readout picker should appear (protocol loaded with readout-defs).
    // The DR readout with IC50 primary intercept renders label "IC50".
    const readoutTrigger = screen.getByRole("combobox", { name: "Readout" });
    fireEvent.click(readoutTrigger);
    const readoutOption = screen.getByRole("option", { name: /IC50/ });
    fireEvent.click(readoutOption);

    // onChange should have been called with a SarColorSpec for drc:rd-1
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining<Partial<SarColorSpec>>({
        column: "drc:rd-1",
        source: "dr_curve",
        protocolId: "proto-1",
      }),
    );
  });
});
