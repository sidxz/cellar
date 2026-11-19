import { describe, expect, it } from "vitest";
import { defaultReadout } from "../components/create-protocol/form-values";
import { readoutDefinitionsPayload } from "./protocol-create-payload";

describe("readoutDefinitionsPayload", () => {
  it("sends the layer a curve fits", () => {
    const [, ic50] = readoutDefinitionsPayload([
      { ...defaultReadout(1), name: "Signal", normalizations: ["percent_inhibition", "z_score"] },
      {
        ...defaultReadout(2),
        name: "IC50",
        data_type: "dose_response",
        dr_y_readout: "Signal",
        dr_y_normalization: "z_score",
      },
    ]);
    expect(ic50.dose_response_config?.y_normalization).toBe("z_score");
  });

  it("sends no layer the Y readout no longer calculates", () => {
    const [, ic50] = readoutDefinitionsPayload([
      { ...defaultReadout(1), name: "Signal", normalizations: [] },
      {
        ...defaultReadout(2),
        name: "IC50",
        data_type: "dose_response",
        dr_y_readout: "Signal",
        dr_y_normalization: "percent_inhibition",
      },
    ]);
    expect(ic50.dose_response_config?.y_normalization).toBeNull();
  });

  it("sends no layer when the curve leaves it to the readout's only one", () => {
    const [, ic50] = readoutDefinitionsPayload([
      { ...defaultReadout(1), name: "Signal", normalizations: ["percent_inhibition"] },
      { ...defaultReadout(2), name: "IC50", data_type: "dose_response", dr_y_readout: "Signal" },
    ]);
    expect(ic50.dose_response_config?.y_normalization).toBeNull();
  });
});
