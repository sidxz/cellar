import { describe, expect, it } from "vitest";
import type { Dataset, DatasetColumn } from "../types";
import { curveSnapshotAt, describeValue, inactiveBadge } from "./value-description";

const numericProv = (aggregation: string, stat?: string) => ({
  protocol_id: "P1",
  readout_definition_id: "s",
  layer: "raw",
  aggregation,
  ...(stat && { stat }),
});
const drProv = (aggregation: string, stat?: string) => ({
  protocol_id: "P1",
  readout_definition_id: "e",
  layer: null,
  aggregation,
  ...(stat && { stat }),
});
const col = (
  key: string,
  label: string,
  provenance: DatasetColumn["provenance"],
  extra: Partial<DatasetColumn> = {},
): DatasetColumn => ({ key, label, kind: "number", provenance, ...extra });

/** Three compounds: a mean over two measured values with one censored value set aside, an
 * all-censored one, and one censored both ways; an IC50 geomean and its pIC50. */
const compounds: Dataset = {
  revision: "r",
  level: "compounds",
  row_count: 3,
  row_ids: ["m1", "m2", "m3"],
  columns: [
    col("compound", "Compound", {}, { kind: "category" }),
    col("rd:s:raw", "Signal (%)", numericProv("mean"), { unit: "%" }),
    col("rd:s:raw:q", "Signal (%) qualifier", numericProv("mean", "qualifier"), {
      kind: "category",
    }),
    col("rd:s:raw:n", "Signal (%) n", numericProv("mean", "n")),
    col("rd:s:raw:sd", "Signal (%) SD", numericProv("mean", "sd"), { unit: "%" }),
    col("rd:s:raw:best", "Signal (%) best", numericProv("mean", "best"), { unit: "%" }),
    col("rd:s:raw:n_censored", "Signal (%) n censored", numericProv("mean", "n_censored")),
    col("dr:e", "Enzyme · IC50", drProv("geomean"), { unit: "µM" }),
    col("dr:e:best", "Enzyme · IC50 best", drProv("geomean", "best"), { unit: "µM" }),
    col("dr:e:n_tested", "Enzyme · IC50 n tested", drProv("geomean", "n_tested")),
    col("dr:e:n_inactive", "Enzyme · IC50 n inactive", drProv("geomean", "n_inactive")),
    col("dr:e:n_used", "Enzyme · IC50 n used", drProv("geomean", "n_used")),
    col("dr:e:p", "Enzyme · pIC50", drProv("p")),
  ],
  values: {
    compound: ["CEL-1", "CEL-2", "CEL-3"],
    "rd:s:raw": [15, 80, null],
    "rd:s:raw:q": [null, ">", null],
    "rd:s:raw:n": [2, 0, 0],
    "rd:s:raw:sd": [7.0710678, null, null],
    "rd:s:raw:best": [20, null, null],
    "rd:s:raw:n_censored": [1, 2, 2],
    "dr:e": [0.31622776, 2, null],
    "dr:e:best": [0.1, 2, null],
    "dr:e:n_tested": [3, 1, null],
    "dr:e:n_inactive": [1, 0, null],
    "dr:e:n_used": [2, 1, null],
    "dr:e:p": [6.5, 5.69897, null],
  },
};

const POINTS = [
  { x: 0.1, y: 10 },
  { x: 1, y: 60 },
];

/** Two run rows: one with a fitted curve, one without points; replicate means. */
const runs: Dataset = {
  revision: "r",
  level: "runs",
  row_count: 2,
  row_ids: ["r1:m1:b1", "r2:m1:b1"],
  columns: [
    col("rd:s:raw", "Signal (%)", numericProv("replicate_mean"), { unit: "%" }),
    col("rd:s:raw:n", "Signal (%) n", numericProv("replicate_mean", "n")),
    col("dr:e", "Enzyme · IC50", drProv("fit"), { unit: "µM" }),
    col("dr:e:top", "top", drProv("fit", "top")),
    col("dr:e:bottom", "bottom", drProv("fit", "bottom")),
    col("dr:e:hill_slope", "Hill slope", drProv("fit", "hill_slope")),
    col("dr:e:r_squared", "R²", drProv("fit", "r_squared")),
    col("dr:e:curve_class", "curve class", drProv("fit", "curve_class"), { kind: "category" }),
    col("dr:e:ci_low", "CI low", drProv("fit", "ci_low"), { hidden: true }),
    col("dr:e:ci_high", "CI high", drProv("fit", "ci_high"), { hidden: true }),
    col("dr:e:points", "points", drProv("fit", "points"), { kind: "text", hidden: true }),
  ],
  values: {
    "rd:s:raw": [42, null],
    "rd:s:raw:n": [3, null],
    "dr:e": [0.3, 0.8],
    "dr:e:top": [100, 98],
    "dr:e:bottom": [0, 2],
    "dr:e:hill_slope": [1.23456, 1],
    "dr:e:r_squared": [0.98765, 0.9],
    "dr:e:curve_class": ["active", "active"],
    "dr:e:ci_low": [0.2, null],
    "dr:e:ci_high": [0.5, null],
    "dr:e:points": [POINTS, null],
  },
};

describe("describeValue", () => {
  it("explains a mean: how many values, SD, best, and the censored ones set aside", () => {
    expect(describeValue(compounds, "rd:s:raw", 0)).toEqual({
      title: "Signal (%)",
      lines: ["Mean of 2 values", "SD 7.071", "Best 20 %", "1 censored value not averaged"],
    });
  });

  it("leaves the arithmetic SD out of a geometric mean", () => {
    const geo: Dataset = {
      ...compounds,
      columns: compounds.columns.map((c) =>
        c.key.startsWith("rd:s:raw")
          ? { ...c, provenance: { ...c.provenance, aggregation: "geomean" } }
          : c,
      ),
    };
    expect(describeValue(geo, "rd:s:raw", 0)?.lines).toEqual([
      "Geometric mean of 2 values",
      "Best 20 %",
      "1 censored value not averaged",
    ]);
  });

  it("says when every value was censored, or censored both ways", () => {
    expect(describeValue(compounds, "rd:s:raw", 1)?.lines).toEqual([
      "All 2 values censored — showing the tightest bound",
    ]);
    expect(describeValue(compounds, "rd:s:raw", 2)?.lines).toEqual([
      "Censored both ways — no value",
    ]);
  });

  it("explains a geometric mean over runs with inactive curves", () => {
    expect(describeValue(compounds, "dr:e", 0)).toEqual({
      title: "Enzyme · IC50",
      lines: ["Geometric mean of 2 of 3 curves", "1 inactive curve", "Best 0.1 µM"],
    });
    expect(describeValue(compounds, "dr:e", 1)?.lines).toEqual([
      "Geometric mean of 1 of 1 curve",
      "Best 2 µM",
    ]);
  });

  it("counts curves censored at the dose bound, and shows the bound when every fit is", () => {
    const censored: Dataset = {
      ...compounds,
      columns: [
        ...compounds.columns,
        col("dr:e:n_censored", "Enzyme · IC50 n censored", drProv("geomean", "n_censored")),
      ],
      values: {
        ...compounds.values,
        "dr:e": [0.31622776, 10, null],
        "dr:e:best": [0.1, null, null],
        "dr:e:n_tested": [4, 3, null],
        "dr:e:n_inactive": [1, 1, null],
        "dr:e:n_used": [2, 0, null],
        "dr:e:n_censored": [1, 2, null],
      },
    };
    expect(describeValue(censored, "dr:e", 0)?.lines).toEqual([
      "Geometric mean of 2 of 4 curves",
      "1 inactive curve",
      "1 censored curve not averaged",
      "Best 0.1 µM",
    ]);
    expect(describeValue(censored, "dr:e", 1)?.lines).toEqual([
      "All 2 fitted curves censored — showing the tightest bound",
      "1 inactive curve",
    ]);
  });

  it("explains a p value", () => {
    expect(describeValue(compounds, "dr:e:p", 0)).toEqual({
      title: "Enzyme · pIC50",
      lines: ["−log10 of the value in M"],
    });
  });

  it("explains one run's fit with its 95% CI, and its replicate mean", () => {
    expect(describeValue(runs, "dr:e", 0)?.lines).toEqual([
      "This run's fit · R² 0.9877 · Hill 1.235",
      "95% CI 0.2–0.5 µM",
    ]);
    expect(describeValue(runs, "rd:s:raw", 0)?.lines).toEqual([
      "Mean of 3 replicate wells in this run",
    ]);
  });

  it("has nothing to say about a Wells value or a cell without data", () => {
    const wells: Dataset = {
      ...runs,
      level: "wells",
      columns: [col("rd:s:raw", "Signal", { readout_definition_id: "s", layer: "raw" })],
    };
    expect(describeValue(wells, "rd:s:raw", 0)).toBeNull();
    expect(describeValue(compounds, "dr:e", 2)).toBeNull();
    expect(describeValue(compounds, "dr:e:p", 2)).toBeNull();
  });
});

describe("inactiveBadge", () => {
  it("counts inactive curves, only when some were inactive", () => {
    expect(inactiveBadge(compounds, "dr:e", 0)).toBe("Inactive 1/3 curves");
    expect(inactiveBadge(compounds, "dr:e", 1)).toBeNull();
    expect(inactiveBadge(compounds, "rd:s:raw", 0)).toBeNull();
  });
});

describe("curveSnapshotAt", () => {
  it("builds the run's curve from its fit siblings and points", () => {
    expect(curveSnapshotAt(runs, "dr:e", 0)).toEqual({
      fitted_value: 0.3,
      fitted_unit: "µM",
      top: 100,
      bottom: 0,
      hill_slope: 1.23456,
      r_squared: 0.98765,
      curve_class: "active",
      confidence_interval_low: 0.2,
      confidence_interval_high: 0.5,
      raw_data: POINTS,
    });
  });

  it("is null without points", () => {
    expect(curveSnapshotAt(runs, "dr:e", 1)).toBeNull();
  });
});
