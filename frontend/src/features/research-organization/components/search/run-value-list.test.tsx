import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ActivityValue, RunSummary } from "../../types";
import { RunValueList } from "./run-value-list";

const CURVE = { fitted_value: 1, top: 100, bottom: 0, hill_slope: 1, raw_data: [] };

function run(i: number, value: number | null, qualifier = "=", curve = true): RunSummary {
  return {
    run_id: `run-${i}`,
    run_date: `2026-0${9 - i}-01`,
    curve_id: curve ? `curve-${i}` : null,
    curve_class: "full",
    r_squared: 0.98,
    intercept_values: [
      { spec: { kind: "ic", level: 50 }, value, qualifier },
      { spec: { kind: "ic", level: 90 }, value: value === null ? null : value * 10, qualifier },
    ],
    curve_snapshot: curve ? CURVE : null,
  };
}

function cell(runs: RunSummary[], run_count = runs.length): ActivityValue {
  return {
    value: 0.26,
    qualifier: null,
    unit: "uM",
    source: "dose_response",
    curve_type: "ic50",
    r_squared: 0.98,
    data_point_count: 10,
    raw_data: null,
    curve_params: null,
    run_count,
    selection_rule: "latest_run",
    runs,
  };
}

const lines = () => screen.getAllByRole("listitem");

describe("RunValueList", () => {
  it("lists each run's value for the column's intercept, newest first, with its run date", () => {
    render(
      <RunValueList
        av={cell([run(1, 0.26), run(2, 500, ">"), run(3, null, "nd")])}
        interceptKey={{ kind: "ic", level: 90 }}
        headerUnit="uM"
        mode="all"
      />,
    );
    expect(lines().map((l) => l.textContent)).toEqual([
      "2.6002026-08-01",
      "> 50002026-07-01",
      "ND2026-06-01",
    ]);
    expect(within(lines()[0]).getByRole("link", { name: "2026-08-01" })).toBeInTheDocument();
  });

  it("marks each fitted run with its curve's colour, in list order", () => {
    render(
      <RunValueList
        av={cell([run(1, 0.26), run(2, 0.16)])}
        interceptKey={{ kind: "ic", level: 50 }}
        mode="all"
      />,
    );
    const dots = lines().map((l) => l.querySelector("[data-run-colour]"));
    expect(dots.map((d) => d?.getAttribute("data-run-colour"))).toEqual(["0", "1"]);
  });

  it("leaves dots out when no run has a curve (single-point readouts)", () => {
    render(
      <RunValueList
        av={cell([run(1, 80, "=", false), run(2, 50, "=", false)])}
        interceptKey={null}
        mode="all"
      />,
    );
    expect(document.querySelector("[data-run-colour]")).toBeNull();
    expect(lines()).toHaveLength(2);
  });

  it("says how many of the runs it shows when the server capped the list", () => {
    render(
      <RunValueList
        av={cell([run(1, 0.26), run(2, 0.16)], 63)}
        interceptKey={{ kind: "ic", level: 50 }}
        mode="all"
      />,
    );
    expect(screen.getByText("Newest 2 of 63")).toBeInTheDocument();
  });

  it("puts the unit on each value only when the header doesn't state it", () => {
    render(
      <RunValueList
        av={cell([run(1, 0.26)])}
        interceptKey={{ kind: "ic", level: 50 }}
        headerUnit={null}
        mode="all"
      />,
    );
    expect(lines()[0].textContent).toBe("0.2600 uM2026-08-01");
  });
});
