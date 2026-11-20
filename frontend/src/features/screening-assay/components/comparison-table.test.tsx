import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ComparisonTable } from "./comparison-table";

const row = (label: string, fitted_value: number, curve_class: "full" | "inactive") => ({
  label,
  color: "#000",
  curve_type: "ic50",
  fitted_value,
  fitted_unit: "uM",
  hill_slope: 1,
  r_squared: 0.9,
  curve_class,
  top: 100,
  bottom: 0,
  raw_data: [0.5, 5, 50, 500].map((concentration) => ({ concentration, response: 5 })),
  intercept_values: null,
});

describe("ComparisonTable", () => {
  it("reads an inactive compound's value as above the top dose, never as the most potent", () => {
    // Run 394e4741: SACC-0108180 inactive over 0.5–500 µM, its fit parked at 37.4.
    render(
      <ComparisonTable
        rows={[row("SACC-0108180", 37.43, "inactive"), row("SACC-0471260", 125.8, "full")]}
      />,
    );
    expect(screen.getByRole("cell", { name: "> 500" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "125.8" })).toHaveAttribute("data-best");
    expect(screen.getByRole("cell", { name: "> 500" })).not.toHaveAttribute("data-best");
  });
});
