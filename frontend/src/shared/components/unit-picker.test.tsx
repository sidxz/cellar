import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { UnitPicker, unitMatches } from "./unit-picker";

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = vi.fn();
});

vi.mock("@/shared/hooks/use-units", () => ({
  useUnits: () => ({
    data: [
      { unit: "µM", group: "Concentration" },
      { unit: "µg/mL", group: "Mass concentration" },
      { unit: "mg/kg", group: "Dose" },
    ],
  }),
}));

describe("unitMatches", () => {
  it("treats u and μ as µ and ignores case", () => {
    expect(unitMatches("µM", "uM")).toBe(true);
    expect(unitMatches("µM", "μm")).toBe(true);
    expect(unitMatches("µg/mL", "ug/ml")).toBe(true);
    expect(unitMatches("mg/kg", "uM")).toBe(false);
  });

  it.each([
    ["RLU", "rlu"],
    ["AU", "au"],
    ["CFU/mL", "cfu"],
    ["log10 CFU", "cfu"],
    ["µM", "UM"],
  ])("finds %s for a query in another case (%s)", (unit, query) => {
    expect(unitMatches(unit, query)).toBe(true);
  });
});

describe("UnitPicker", () => {
  it("suggests the canonical unit for a variant spelling and keeps free text", () => {
    const onChange = vi.fn();
    const { rerender } = render(<UnitPicker value="" onChange={onChange} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "uM" } });
    expect(onChange).toHaveBeenLastCalledWith("uM");
    rerender(<UnitPicker value="uM" onChange={onChange} />);
    fireEvent.focus(screen.getByRole("combobox"));
    fireEvent.click(screen.getByText("µM"));
    expect(onChange).toHaveBeenLastCalledWith("µM");
  });
});
