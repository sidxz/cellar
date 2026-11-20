import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { crossProtocol } from "../../lib/cross-protocol-fixture";
import type { Dataset, DatasetColumn } from "../../types";
import { ValueCell } from "./value-cell";

const prov = (aggregation: string, stat?: string, layer: string | null = "raw") => ({
  protocol_id: "P1",
  readout_definition_id: "s",
  layer,
  aggregation,
  ...(stat && { stat }),
});
const col = (key: string, provenance: DatasetColumn["provenance"]): DatasetColumn => ({
  key,
  label: key === "rd:s:raw" ? "Signal (%)" : key,
  kind: "number",
  provenance,
});

const ds: Dataset = {
  revision: "r",
  level: "compounds",
  row_count: 2,
  row_ids: ["m1", "m2"],
  columns: [
    col("rd:s:raw", prov("mean")),
    col("rd:s:raw:q", prov("mean", "qualifier")),
    col("rd:s:raw:n", prov("mean", "n")),
    col("rd:s:raw:n_censored", prov("mean", "n_censored")),
    col("dr:e", prov("geomean", undefined, null)),
    col("dr:e:n_tested", prov("geomean", "n_tested", null)),
    col("dr:e:n_inactive", prov("geomean", "n_inactive", null)),
    col("dr:e:n_used", prov("geomean", "n_used", null)),
  ],
  values: {
    "rd:s:raw": [80, null],
    "rd:s:raw:q": [">", null],
    "rd:s:raw:n": [0, null],
    "rd:s:raw:n_censored": [2, null],
    "dr:e": [null, null],
    "dr:e:n_tested": [3, null],
    "dr:e:n_inactive": [3, null],
    "dr:e:n_used": [0, null],
  },
};

describe("ValueCell", () => {
  it("shows the qualifier before the number and explains the value in a popover", () => {
    render(<ValueCell ds={ds} valueKey="rd:s:raw" i={0} />);
    const trigger = screen.getByRole("button", { name: /> 80/ });
    // A native button: reachable by Tab, opened with Enter or Space.
    expect(trigger.tagName).toBe("BUTTON");
    expect(trigger).not.toHaveAttribute("tabindex", "-1");
    fireEvent.click(trigger);
    expect(screen.getByText("Signal (%)")).toBeInTheDocument();
    expect(
      screen.getByText("All 2 values censored — showing the tightest bound"),
    ).toBeInTheDocument();
  });

  it("shows a dash and the inactive badge for an all-inactive geomean", () => {
    render(<ValueCell ds={ds} valueKey="dr:e" i={0} />);
    expect(screen.getByText("Inactive 3/3 curves")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /—/ }));
    expect(screen.getByText("Geometric mean of 0 of 3 curves")).toBeInTheDocument();
  });

  it("shows inclusive qualifiers as ≥ and ≤, in the cell and its name", () => {
    const inclusive: Dataset = {
      ...ds,
      values: {
        ...ds.values,
        "rd:s:raw": [80, 5],
        "rd:s:raw:q": [">=", "<="],
        "rd:s:raw:n_censored": [2, 1],
      },
    };
    render(<ValueCell ds={inclusive} valueKey="rd:s:raw" i={0} />);
    expect(
      screen.getByRole("button", { name: "≥ 80, how Signal (%) was computed" }),
    ).toHaveTextContent("≥ 80");
    render(<ValueCell ds={inclusive} valueKey="rd:s:raw" i={1} />);
    expect(screen.getByRole("button", { name: /^≤ 5,/ })).toBeInTheDocument();
  });

  it("shows a plain dash, with nothing to open, when the row has no data", () => {
    render(<ValueCell ds={ds} valueKey="rd:s:raw" i={1} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("says briefly why a compared protocol's value is missing, the full reason on hover", () => {
    const { rerender } = render(<ValueCell ds={crossProtocol} valueKey="dr:y:p" i={1} />);
    const short = screen.getByText("not tested");
    expect(short).toHaveAttribute("title", "Not tested in Counter");
    expect(screen.getByText("Not tested in Counter")).toBeInTheDocument();
    rerender(<ValueCell ds={crossProtocol} valueKey="sel:dr:x:p|dr:y:p" i={2} />);
    expect(screen.getByText("no value")).toHaveAttribute("title", "No value");
    rerender(<ValueCell ds={crossProtocol} valueKey="sel:dr:x:p|dr:y:p" i={0} />);
    expect(
      screen.getByRole("button", {
        name: "2, how Δ (Primary · pIC50) − (Counter · pIC50) was computed",
      }),
    ).toBeInTheDocument();
  });
});
