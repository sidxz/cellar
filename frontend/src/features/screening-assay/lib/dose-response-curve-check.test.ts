import { describe, expect, it } from "vitest";
import { type ProtocolFormValues, defaultReadout } from "../components/create-protocol/form-values";
import { curveAxisRenames, curveProblem, fittedLayer, yLayers } from "./dose-response-curve-check";
import { WELL_CONC_X } from "./readout-constants";

type Row = ProtocolFormValues["readouts"][number];

const signal = (over: Partial<Row> = {}): Row => ({
  ...defaultReadout(1),
  name: "Signal",
  normalizations: ["percent_inhibition"],
  ...over,
});
const curve = (over: Partial<Row> = {}): Row => ({
  ...defaultReadout(2),
  name: "IC50",
  data_type: "dose_response",
  dr_y_readout: "Signal",
  dr_y_normalization: "percent_inhibition",
  ...over,
});

describe("yLayers", () => {
  it("lists the calculated layers of the numeric readout, sorted, without none", () => {
    const rows = [signal({ normalizations: ["z_score", "none", "percent_inhibition"] })];
    expect(yLayers(rows, "Signal")).toEqual(["percent_inhibition", "z_score"]);
  });

  it("is empty for a readout that is missing or not numeric", () => {
    expect(yLayers([signal()], "Other")).toEqual([]);
    expect(yLayers([signal({ data_type: "text" })], "Signal")).toEqual([]);
  });
});

describe("curveProblem", () => {
  it("is null for a curve on a numeric readout with its layer", () => {
    const rows = [signal(), curve()];
    expect(curveProblem(rows[1], rows)).toBeNull();
  });

  it("is null for a readout that is not a curve", () => {
    expect(curveProblem(signal(), [signal()])).toBeNull();
  });

  it("asks for a Y readout when none is chosen", () => {
    const rows = [signal(), curve({ dr_y_readout: "" })];
    expect(curveProblem(rows[1], rows)).toBe("Choose the readout this curve fits.");
  });

  it("names a Y readout that no longer exists", () => {
    const rows = [signal({ name: "THF Fluorescence Slope" }), curve()];
    expect(curveProblem(rows[1], rows)).toBe(
      "'Signal' is not a numeric readout of this protocol. Choose the readout this curve fits.",
    );
  });

  it("names an X readout that does not exist", () => {
    const rows = [signal(), curve({ dr_x_readout: "Conc" })];
    expect(curveProblem(rows[1], rows)).toBe("'Conc' is not a readout of this protocol.");
  });

  it("accepts well concentration as X", () => {
    const rows = [signal(), curve({ dr_x_readout: WELL_CONC_X })];
    expect(curveProblem(rows[1], rows)).toBeNull();
  });

  it("treats a layer the Y readout no longer calculates as unset", () => {
    const one = [signal(), curve({ dr_y_normalization: "z_score" })];
    expect(curveProblem(one[1], one)).toBeNull();
    const two = [
      signal({ normalizations: ["percent_inhibition", "percent_activation"] }),
      curve({ dr_y_normalization: "z_score" }),
    ];
    expect(curveProblem(two[1], two)).toBe("Choose which layer of 'Signal' this curve fits.");
  });

  it("asks for a layer when the Y readout calculates two", () => {
    const rows = [
      signal({ normalizations: ["percent_inhibition", "z_score"] }),
      curve({ dr_y_normalization: "" }),
    ];
    expect(curveProblem(rows[1], rows)).toBe("Choose which layer of 'Signal' this curve fits.");
  });
});

describe("fittedLayer", () => {
  it("is the chosen layer while the Y readout calculates it, else unset", () => {
    const rows = [signal({ normalizations: ["percent_inhibition", "z_score"] }), curve()];
    expect(fittedLayer(rows[1], rows)).toBe("percent_inhibition");
    expect(fittedLayer(curve({ dr_y_normalization: "percent_control" }), rows)).toBe("");
  });
});

describe("curveAxisRenames", () => {
  it("moves the X and Y of curves that plot the renamed readout", () => {
    const rows = [signal(), curve({ dr_x_readout: "Signal" })];
    expect(curveAxisRenames(rows, 0, "Signal", "THF Fluorescence Slope")).toEqual([
      { index: 1, field: "dr_x_readout", value: "THF Fluorescence Slope" },
      { index: 1, field: "dr_y_readout", value: "THF Fluorescence Slope" },
    ]);
  });

  it("compares names trimmed", () => {
    const rows = [signal(), curve()];
    expect(curveAxisRenames(rows, 0, " Signal ", "Slope ")).toEqual([
      { index: 1, field: "dr_y_readout", value: "Slope" },
    ]);
  });

  it("does nothing when the old or new name is empty", () => {
    const rows = [signal(), curve({ dr_y_readout: "" })];
    expect(curveAxisRenames(rows, 0, "", "T")).toEqual([]);
    expect(curveAxisRenames([signal(), curve()], 0, "Signal", "")).toEqual([]);
  });

  it("leaves a curve on its readout while a new readout's name is typed through it", () => {
    // Typing "Signal bg" in a new row passes through "Signal", the name the IC50 fits.
    const rows = [signal(), curve(), signal({ name: "Signal", normalizations: [] })];
    expect(curveAxisRenames(rows, 2, "Signal", "Signal ")).toEqual([]);
    expect(curveAxisRenames(rows, 2, "Signal ", "Signal b")).toEqual([]);
  });

  it("leaves a curve on its readout while another readout's name is backspaced through it", () => {
    const rows = [signal(), curve(), signal({ name: "Signal b", normalizations: [] })];
    expect(curveAxisRenames(rows, 2, "Signal b", "Signal")).toEqual([]);
    const through = [signal(), curve(), signal({ name: "Signal", normalizations: [] })];
    expect(curveAxisRenames(through, 2, "Signal", "Signa")).toEqual([]);
  });
});
