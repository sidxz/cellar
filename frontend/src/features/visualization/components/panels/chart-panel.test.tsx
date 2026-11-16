import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { dataset, panel } from "../../lib/traces/test-fixtures";
import { WorkbenchProvider } from "../../store/workbench-context";
import { ChartPanel } from "./chart-panel";

const plot = vi.hoisted(() => ({ last: null as unknown }));
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (p: unknown) => {
    plot.last = p;
    return null;
  },
}));
vi.mock("@/shared/components/chemistry", () => ({
  StructureThumbnail: ({ smiles }: { smiles: string }) => <img alt={`structure ${smiles}`} />,
}));
const hover = (ev: unknown) =>
  act(() => (plot.last as { onHover: (e: unknown) => void }).onHover(ev));

const ds = dataset(
  {
    compound: ["CEL-1", "CEL-2"],
    structure: ["c1ccccc1", "CCO"],
    well_type: ["sample", "sample"],
    y: [5, 7],
  },
  { structure: "structure" },
);
const box = panel("box", { category: "well_type", y: "y" });
const show = () =>
  render(
    <WorkbenchProvider initialPanels={[box]}>
      <ChartPanel panel={box} ds={ds} />
    </WorkbenchProvider>,
  );
const rect = (width: number, height: number) =>
  ({ x: 0, y: 0, left: 0, top: 0, right: width, bottom: height, width, height }) as DOMRect;

afterEach(() => vi.restoreAllMocks());

describe("ChartPanel", () => {
  it("shows a box point's compound card, and a box's median and quartiles over the box", () => {
    render(
      <WorkbenchProvider initialPanels={[box]}>
        <ChartPanel panel={box} ds={ds} />
      </WorkbenchProvider>,
    );
    hover({ points: [{ customdata: 1 }], event: { clientX: 1, clientY: 1 } });
    expect(screen.getByRole("tooltip")).toHaveTextContent("CEL-2");
    expect(screen.getByAltText("structure CCO")).toBeInTheDocument();

    const data = { name: "Sample", y: [5, 7] };
    hover({
      points: [7, 7, 7, 6, 5, 5, 5].map((y) => ({ y, hoverOnBox: true, customdata: 0, data })),
      event: { clientX: 1, clientY: 1 },
    });
    const card = screen.getByRole("tooltip");
    expect(card).toHaveTextContent("Sample");
    expect(card).toHaveTextContent("Median6");
    expect(card).not.toHaveTextContent("CEL-1");
  });

  it("keeps the whole card inside the window, beside the cursor where there is room", () => {
    const CARD = { w: 224, h: 240 };
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (
      this: Element,
    ) {
      return this.getAttribute("role") === "tooltip" ? rect(CARD.w, CARD.h) : rect(600, 300);
    });
    show();
    const at = (x: number, y: number) => {
      hover({ points: [{ customdata: 0 }], event: { clientX: x, clientY: y } });
      const { left, top } = screen.getByRole("tooltip").style;
      return [Number.parseFloat(left), Number.parseFloat(top)];
    };
    const W = window.innerWidth;
    const H = window.innerHeight;
    // Room on both sides: just right of and below the cursor.
    expect(at(500, 300)).toEqual([512, 312]);
    // Near the right and bottom edges: left of and above it.
    expect(at(1000, 700)).toEqual([1000 - 12 - CARD.w, 700 - 12 - CARD.h]);
    for (const [x, y] of [
      [0, 0],
      [W / 2, H / 2],
      [W, H],
      [W - 100, 10],
      [5, H - 5],
    ]) {
      const [left, top] = at(x, y);
      expect(left, `${x},${y}`).toBeGreaterThanOrEqual(0);
      expect(left + CARD.w, `${x},${y}`).toBeLessThanOrEqual(W);
      expect(top, `${x},${y}`).toBeGreaterThanOrEqual(0);
      expect(top + CARD.h, `${x},${y}`).toBeLessThanOrEqual(H);
    }
    // A window too short for the card on either side of the cursor: moved, never cut.
    vi.spyOn(window, "innerHeight", "get").mockReturnValue(300);
    const [, top] = at(500, 150);
    expect(top).toBeGreaterThanOrEqual(0);
    expect(top + CARD.h).toBeLessThanOrEqual(300);
  });

  it("keeps the last structure on screen until the next one is drawn", () => {
    show();
    const event = { clientX: 1, clientY: 1 };
    hover({ points: [{ customdata: 0 }], event });
    const first = screen.getByAltText("structure c1ccccc1");
    expect(first).toBeVisible();

    hover({ points: [{ customdata: 1 }], event });
    expect(screen.getByRole("tooltip")).toHaveTextContent("CEL-2");
    // The same drawing, not drawn again, while the next one is made out of sight.
    expect(screen.getByAltText("structure c1ccccc1")).toBe(first);
    expect(first).toBeVisible();
    expect(screen.getByAltText("structure CCO")).not.toBeVisible();

    fireEvent.load(screen.getByAltText("structure CCO"));
    expect(screen.queryByAltText("structure c1ccccc1")).toBeNull();
    expect(screen.getByAltText("structure CCO")).toBeVisible();
  });
});
