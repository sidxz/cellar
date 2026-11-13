import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DeltaTmHint } from "./delta-tm-hint";

const HINT =
  /Typical: outside −2 to 2 °C \(Thermo Fisher Protein Thermal Shift guide; MIT nanoDSF SOP\)/;

describe("DeltaTmHint", () => {
  it("shows the typical-value hint only for a ΔTm readout", () => {
    const { rerender } = render(<DeltaTmHint readout={{ melt_config: { measure: "delta_tm" } }} />);
    expect(screen.getByText(HINT)).toBeInTheDocument();

    rerender(<DeltaTmHint readout={{ melt_config: { measure: "tm" } }} />);
    expect(screen.queryByText(HINT)).not.toBeInTheDocument();
    rerender(<DeltaTmHint readout={{ melt_config: null }} />);
    expect(screen.queryByText(HINT)).not.toBeInTheDocument();
    rerender(<DeltaTmHint readout={undefined} />);
    expect(screen.queryByText(HINT)).not.toBeInTheDocument();
  });
});
