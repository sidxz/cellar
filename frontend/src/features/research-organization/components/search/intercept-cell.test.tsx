import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { InterceptCell } from "./intercept-cell";
import type { ActivityValue } from "@/features/research-organization/types";

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
            log_value_sd: 0.50,
          },
          disagreement_flag: true,
        },
      ],
    };
    render(<InterceptCell av={disagreed} spec={null} isPrimary={true} mode="latest" />);
    expect(screen.getByLabelText(/runs disagree/i)).toBeTruthy();
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
          intercept_values: [
            { spec: { kind: "ic", level: 50.0 }, value: 0.10, at_bound: false },
          ],
        },
        {
          run_id: "r2",
          run_date: "2026-02-08",
          curve_id: "c2",
          curve_class: "full",
          r_squared: 0.97,
          intercept_values: [
            { spec: { kind: "ic", level: 50.0 }, value: 0.18, at_bound: false },
          ],
        },
      ],
      intercept_aggregates: [
        {
          spec: { kind: "ic", level: 50.0 },
          selected_value: 0.10,
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
      <InterceptCell
        av={av}
        spec={{ kind: "ic", level: 50.0 }}
        isPrimary={false}
        mode="latest"
      />,
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
