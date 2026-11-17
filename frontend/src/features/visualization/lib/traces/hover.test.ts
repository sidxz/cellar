import { describe, expect, it } from "vitest";
import { crossProtocol } from "../cross-protocol-fixture";
import { boxSummary, hoverInfo } from "./hover";
import { dataset } from "./test-fixtures";

const wells = () =>
  dataset(
    {
      compound: ["CEL-1", null, null],
      structure: ["c1ccccc1", null, null],
      run: ["RUN-7", "RUN-7", "RUN-7"],
      plate: ["Plate 1", "Plate 1", "RUN-7 · Plate 2"],
      well: ["B07", "A01", "P24"],
      label: [null, null, "MadR"],
      well_order: [31, 1, 384],
      y: [42.5, 3, 7],
      "y:q": [">", null, null],
      "y:outlier": [null, "outlier", null],
      well_type: ["sample", "negative_control", "reference"],
    },
    { structure: "structure", label: "text" },
  );

describe("hoverInfo", () => {
  it("names the compound, draws its structure, places it and lists the plotted values once", () => {
    const fields = ["well_order", "y", "compound", "well_type", "y"];
    expect(hoverInfo(wells(), 0, fields)).toEqual({
      structure: "c1ccccc1",
      title: "CEL-1",
      place: "RUN-7 · Plate 1 B07",
      lines: [
        { label: "well_order", value: "31" },
        { label: "Signal", value: "> 42.5" },
        { label: "well_type", value: "Sample" },
      ],
    });
  });

  it("says a flagged value is an outlier", () => {
    expect(hoverInfo(wells(), 1, ["y"]).lines).toEqual([{ label: "Signal", value: "3 · Outlier" }]);
    expect(hoverInfo(wells(), 0, ["y"]).lines).toEqual([{ label: "Signal", value: "> 42.5" }]);
  });

  it("titles a well without a compound by its label, else its role, as the table does", () => {
    const ds = wells();
    expect(hoverInfo(ds, 1, ["y"])).toMatchObject({
      structure: null,
      title: "Negative control",
      place: "RUN-7 · Plate 1 A01",
    });
    const sample = { ...ds, values: { ...ds.values, well_type: ["sample", "sample", null] } };
    expect(hoverInfo(sample, 1, ["y"]).title).toBe("No compound");
    // A plate label that already names its run does not repeat it.
    expect(hoverInfo(ds, 2, ["y"])).toMatchObject({ title: "MadR", place: "RUN-7 · Plate 2 P24" });
  });

  it("says why a compared value is missing, a long protocol name cut in the middle", () => {
    const info = hoverInfo(crossProtocol, 1, ["dr:x:p", "dr:y:p"]);
    expect(info.lines).toEqual([
      { label: "Primary · pIC50", value: "6" },
      { label: "Counter · pIC50", value: "Not tested in Counter" },
    ]);
    expect(hoverInfo(crossProtocol, 2, ["dr:y:p"]).lines).toEqual([
      { label: "Counter · pIC50", value: "No value" },
    ]);
    const name = "M. tuberculosis InhA inhibition [DD-CoA fluorescence]";
    const long = {
      ...crossProtocol,
      protocols: [
        crossProtocol.protocols?.[0] ?? { protocol_id: "A", name: "Primary" },
        { protocol_id: "B", name },
      ],
    };
    expect(hoverInfo(long, 1, ["dr:y:p"]).lines[0].value).toBe(
      "Not tested in M. tubercu…[DD-CoA fluorescence]",
    );
  });
});

describe("boxSummary", () => {
  it("reads a box's median, quartiles, fences and range from Plotly's own hover values", () => {
    // Plotly sends max, upper fence, Q3, median, Q1, lower fence, min (in any order).
    const points = [9, 8, 6, 5, 4, 2, 1].reverse().map((y) => ({
      y,
      hoverOnBox: true,
      data: { name: "Sample", y: [1, 2, 4, 5, 6, 8, 9, 5] },
    }));
    expect(boxSummary(points)).toEqual({
      title: "Sample",
      lines: [
        { label: "Median", value: "5" },
        { label: "Q1 – Q3", value: "4 – 6" },
        { label: "Fences", value: "2 – 8" },
        { label: "Min – Max", value: "1 – 9" },
        { label: "n", value: "8" },
      ],
    });
    // Anything else (a box mean, a newer Plotly) still names the box and counts it.
    expect(boxSummary(points.slice(1))).toEqual({
      title: "Sample",
      lines: [{ label: "n", value: "8" }],
    });
  });
});
