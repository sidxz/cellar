import { WELL_TYPE_COLORS, wellTypeColors } from "@/shared/lib/chart-colors";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PlateMapEditor } from "./plate-map-editor";
import { PlateMapView } from "./plate-map-view";

const MAP = { A1: "positive_control", A2: "negative_control" } as const;
const bg = (title: string) => (screen.getByTitle(title) as HTMLElement).style.background;
// jsdom normalises colours (hex → rgb); compare through the same normalisation.
const css = (color: string | undefined) => {
  const el = document.createElement("div");
  el.style.background = color ?? "";
  return el.style.background;
};

// The role → colour convention itself is tested in shared/lib/chart-colors.test.ts.
describe("control layouts", () => {
  it.each([
    ["the protocol's colours", wellTypeColors("low")],
    ["the default convention", undefined],
  ])("draws each control well in its role's colour from %s", (_, colors) => {
    const expected = colors ?? WELL_TYPE_COLORS;
    render(<PlateMapView format="96" templateMap={MAP} colors={colors} />);
    expect(bg("A1: Positive Control")).toBe(css(expected.positive_control));
    expect(bg("A2: Negative Control")).toBe(css(expected.negative_control));
  });

  it("the layout editor draws controls in the default convention's colours", () => {
    render(<PlateMapEditor format="96" value={MAP} onChange={() => {}} />);
    expect(bg("A1: Positive Control")).toBe(css(WELL_TYPE_COLORS.positive_control));
    expect(bg("A2: Negative Control")).toBe(css(WELL_TYPE_COLORS.negative_control));
  });
});
