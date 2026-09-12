import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CompoundValueCell, type CompoundValueCellProps, isReportedEndpoint } from "./results-grid";

function renderCell(overrides: Partial<CompoundValueCellProps> = {}) {
  return render(
    <CompoundValueCell
      prefix=""
      value={13.6}
      unit="uM"
      replicates={null}
      verdict={null}
      overridden={false}
      overrideReason={null}
      reported={false}
      readOnly
      onEdit={() => {}}
      {...overrides}
    />,
  );
}

describe("CompoundValueCell reported marker", () => {
  it("shows the reported chip for a DR measurement sourced from an endpoint row", () => {
    const reported = isReportedEndpoint(true, { source_readout_id: "rd-1", source_curve_id: null });
    expect(reported).toBe(true);

    renderCell({ reported });
    expect(screen.getByText("reported")).toHaveAttribute(
      "title",
      "Reported endpoint — no fitted curve for this compound",
    );
  });

  it("shows no chip for a DR measurement backed by a fitted curve", () => {
    const reported = isReportedEndpoint(true, { source_readout_id: null, source_curve_id: "c-1" });
    expect(reported).toBe(false);

    renderCell({ reported });
    expect(screen.queryByText("reported")).toBeNull();
  });

  it("shows no chip on a non-DR channel even when a readout id is present", () => {
    const reported = isReportedEndpoint(false, {
      source_readout_id: "rd-1",
      source_curve_id: null,
    });
    expect(reported).toBe(false);

    renderCell({ reported });
    expect(screen.queryByText("reported")).toBeNull();
  });

  it("keeps the chip on the marker line beside the verdict chip", () => {
    renderCell({ reported: true, verdict: "pass" });
    const chip = screen.getByText("reported");
    const markerLine = chip.parentElement;
    expect(markerLine).toHaveTextContent("pass");
    // Value stays on its own line above the markers so the 120px column
    // never clips it.
    expect(markerLine).not.toHaveTextContent("13.6");
  });
});
