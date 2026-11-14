import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ActivityValue } from "../../types";
import { RunHistoryTooltip } from "./run-history-tooltip";

function singlePoint(values: Array<{ value: number | null; qualifier: string }>): ActivityValue {
  return {
    value: 80,
    qualifier: null,
    unit: "%",
    source: "readout",
    curve_type: null,
    r_squared: null,
    data_point_count: values.length,
    raw_data: null,
    curve_params: null,
    run_count: values.length,
    runs: values.map((v, i) => ({
      run_id: `r${i}`,
      run_date: `2026-0${i + 1}-01`,
      curve_id: null,
      curve_class: null,
      r_squared: null,
      intercept_values: [{ spec: { kind: "value" }, value: v.value, qualifier: v.qualifier }],
    })),
  };
}

describe("RunHistoryTooltip — single-point runs", () => {
  it("lists each run's value with its qualifier", () => {
    render(
      <RunHistoryTooltip
        av={singlePoint([
          { value: 80, qualifier: "=" },
          { value: 50, qualifier: ">" },
          { value: null, qualifier: "nd" },
        ])}
        interceptKey={null}
        unit="%"
      />,
    );
    expect(screen.getByText("80.0 %")).toBeInTheDocument();
    expect(screen.getByText("> 50.0 %")).toBeInTheDocument();
    expect(screen.getByText("ND")).toBeInTheDocument();
  });
});
