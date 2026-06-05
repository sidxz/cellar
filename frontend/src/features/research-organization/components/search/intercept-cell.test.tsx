import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ActivityValue } from "@/features/research-organization/types";
import { InterceptCell } from "./intercept-cell";

const baseAv: ActivityValue = {
  value: 0.12,
  qualifier: "=",
  unit: "uM",
  source: "dose_response",
  curve_type: null,
  r_squared: null,
  data_point_count: 1,
  raw_data: null,
  curve_params: null,
  run_count: 1,
  selection_rule: "latest_approved_run",
  runs: null,
  intercept_aggregates: null,
  disagreement_flag: false,
};

describe("<InterceptCell />", () => {
  it("renders just the value for a single-run cell", () => {
    render(<InterceptCell av={baseAv} spec={null} isPrimary={true} mode="latest" />);
    expect(screen.getByText(/0\.12/)).toBeTruthy();
    expect(screen.queryByText(/₃/)).toBeNull();
  });

  it("renders subscript for multi-run cell", () => {
    const multi: ActivityValue = {
      ...baseAv,
      run_count: 3,
      intercept_aggregates: [
        {
          spec: { kind: "primary" },
          selected_value: 0.12,
          selected_qualifier: "=",
          aggregate_stats: {
            geometric_mean: 0.13,
            fold_range: 1.4,
            log_value_mean: -0.89,
            log_value_sd: 0.07,
          },
          disagreement_flag: false,
        },
      ],
    };
    render(<InterceptCell av={multi} spec={null} isPrimary={true} mode="latest" />);
    expect(screen.getByText(/₃/)).toBeTruthy();
  });

  it("shows warning glyph when disagreement_flag is true on the matching aggregate", () => {
    const disagreed: ActivityValue = {
      ...baseAv,
      run_count: 4,
      intercept_aggregates: [
        {
          spec: { kind: "primary" },
          selected_value: 0.45,
          selected_qualifier: "=",
          aggregate_stats: {
            geometric_mean: 0.45,
            fold_range: 12.0,
            log_value_mean: -0.35,
            log_value_sd: 0.5,
          },
          disagreement_flag: true,
        },
      ],
    };
    render(<InterceptCell av={disagreed} spec={null} isPrimary={true} mode="latest" />);
    expect(screen.getByLabelText(/runs disagree/i)).toBeTruthy();
  });

  it("multi-run Latest cell shows muted gmean + pX summary lines under headline", () => {
    const av: ActivityValue = {
      ...baseAv,
      run_count: 3,
      intercept_aggregates: [
        {
          spec: { kind: "ic", level: 50.0 },
          selected_value: 0.1,
          selected_qualifier: "=",
          aggregate_stats: {
            geometric_mean: 0.18,
            fold_range: 4.2,
            log_value_mean: -0.74, // log10(0.18); pIC50 (µM) = 6 - (-0.74) = 6.74
            log_value_sd: 0.3,
          },
          disagreement_flag: false,
        },
      ],
    };
    render(
      <InterceptCell av={av} spec={{ kind: "ic", level: 50.0 }} isPrimary={false} mode="latest" />,
    );
    // gmean line: shows geometric mean with 3 sig figs + fold-range chip
    expect(screen.getByText(/gmean.*0\.180.*×4\.2/)).toBeTruthy();
    // pX line: label is pIC50, value 6.74, ± 0.30
    expect(screen.getByText(/pIC50.*6\.74.*±.*0\.30/)).toBeTruthy();
  });

  it("multi-run Geometric mean cell skips the gmean line (it's the headline) but keeps pX", () => {
    const av: ActivityValue = {
      ...baseAv,
      run_count: 3,
      intercept_aggregates: [
        {
          spec: { kind: "ec", level: 90.0 },
          selected_value: 0.45,
          selected_qualifier: "=",
          aggregate_stats: {
            geometric_mean: 0.45,
            fold_range: 4.0,
            log_value_mean: -0.35,
            log_value_sd: 0.2,
          },
          disagreement_flag: false,
        },
      ],
    };
    render(
      <InterceptCell av={av} spec={{ kind: "ec", level: 90.0 }} isPrimary={false} mode="gmean" />,
    );
    // No gmean line — it's redundant when the headline IS the geometric mean
    expect(screen.queryByText(/gmean/)).toBeNull();
    // pX line still shows with pEC90 label (kind=ec, level=90)
    expect(screen.getByText(/pEC90.*6\.35.*±.*0\.20/)).toBeTruthy();
  });

  it("multi-run ND cell skips the aggregate summary lines (nothing to summarize)", () => {
    const av: ActivityValue = {
      ...baseAv,
      value: null,
      curve_params: { curve_class: "inactive" } as ActivityValue["curve_params"],
      run_count: 5,
      intercept_aggregates: [
        {
          spec: { kind: "primary" },
          selected_value: null,
          selected_qualifier: "nd",
          // BE returns all-None stats when no EQ run contributes
          aggregate_stats: {
            geometric_mean: null,
            fold_range: null,
            log_value_mean: null,
            log_value_sd: null,
          },
          disagreement_flag: false,
        },
      ],
    };
    render(<InterceptCell av={av} spec={null} isPrimary={true} mode="latest" />);
    expect(screen.queryByText(/gmean/)).toBeNull();
    expect(screen.queryByText(/pIC|pEC|pX/)).toBeNull();
  });

  it("single-run cell shows no aggregate summary lines", () => {
    // run_count=1 default; nothing to aggregate, no muted lines
    render(<InterceptCell av={baseAv} spec={null} isPrimary={true} mode="latest" />);
    expect(screen.queryByText(/gmean/)).toBeNull();
    expect(screen.queryByText(/±/)).toBeNull();
  });

  it("opens popover with per-run table on click", async () => {
    const av: ActivityValue = {
      ...baseAv,
      run_count: 2,
      runs: [
        {
          run_id: "r1",
          run_date: "2026-04-12",
          curve_id: "c1",
          curve_class: "full",
          r_squared: 0.99,
          intercept_values: [{ spec: { kind: "ic", level: 50.0 }, value: 0.1, at_bound: false }],
        },
        {
          run_id: "r2",
          run_date: "2026-02-08",
          curve_id: "c2",
          curve_class: "full",
          r_squared: 0.97,
          intercept_values: [{ spec: { kind: "ic", level: 50.0 }, value: 0.18, at_bound: false }],
        },
      ],
      intercept_aggregates: [
        {
          spec: { kind: "ic", level: 50.0 },
          selected_value: 0.1,
          selected_qualifier: "=",
          aggregate_stats: {
            geometric_mean: 0.13,
            fold_range: 1.8,
            log_value_mean: -0.88,
            log_value_sd: 0.13,
          },
          disagreement_flag: false,
        },
      ],
    };
    render(
      <InterceptCell av={av} spec={{ kind: "ic", level: 50.0 }} isPrimary={false} mode="latest" />,
    );
    // Click to open Popover (Popover defaults to click-trigger, not hover).
    const trigger = screen.getByRole("button", { name: /show run history/i });
    fireEvent.click(trigger);
    await waitFor(() => {
      // Date columns and stats footer text — values may be split across
      // sibling text nodes inside the same element, so match only the
      // innermost element whose own textContent (excluding child element
      // textContent) hits the pattern.
      const byOwnText = (re: RegExp) => {
        const all = Array.from(document.querySelectorAll("*"));
        const hits = all.filter((el) => {
          // Walk direct text-node children only — ignore element children.
          const ownText = Array.from(el.childNodes)
            .filter((n) => n.nodeType === Node.TEXT_NODE)
            .map((n) => n.textContent ?? "")
            .join("");
          return re.test(ownText);
        });
        return hits[0] ?? null;
      };
      expect(byOwnText(/2026-04-12/)).toBeTruthy();
      expect(byOwnText(/2026-02-08/)).toBeTruthy();
      expect(byOwnText(/Geometric mean/)).toBeTruthy();
      expect(byOwnText(/0\.130/)).toBeTruthy(); // gmean to precision(3)
      expect(byOwnText(/Fold-range/)).toBeTruthy();
      expect(byOwnText(/1\.8/)).toBeTruthy();
    });
  });
});
