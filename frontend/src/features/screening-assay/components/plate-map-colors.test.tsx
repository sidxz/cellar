import { wellTypeColors } from "@/shared/lib/chart-colors";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PlateMapEditor } from "./plate-map-editor";
import { PlateMapView } from "./plate-map-view";

const RED = "rgb(220, 38, 38)";
const BLUE = "rgb(37, 99, 235)";
const MAP = { A1: "positive_control", A2: "negative_control" } as const;
const bg = (title: string) => (screen.getByTitle(title) as HTMLElement).style.background;

// Layouts draw controls by effect, as the run heat maps do: full-effect red, no effect blue.
describe("control layouts", () => {
  it("the protocol's layout follows its convention", () => {
    render(<PlateMapView format="96" templateMap={MAP} colors={wellTypeColors("low")} />);
    expect(bg("A1: Positive Control")).toBe(RED);
    expect(bg("A2: Negative Control")).toBe(BLUE);
  });

  it("a layout outside a protocol uses the default convention", () => {
    render(<PlateMapView format="96" templateMap={MAP} />);
    expect(bg("A1: Positive Control")).toBe(BLUE);
    expect(bg("A2: Negative Control")).toBe(RED);
  });

  it("the layout editor draws the same colours, never green", () => {
    render(<PlateMapEditor format="96" value={MAP} onChange={() => {}} />);
    expect(bg("A1: Positive Control")).toBe(BLUE);
    expect(bg("A2: Negative Control")).toBe(RED);
  });
});
