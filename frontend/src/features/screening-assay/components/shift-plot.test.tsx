import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

type P = {
  data: Record<string, any>[];
  layout: Record<string, any>;
  config: Record<string, unknown>;
  onClick?: (e: unknown) => void;
  onHover?: (e: unknown) => void;
  onUnhover?: () => void;
};
vi.mock("@/shared/components/chemistry/structure-thumbnail", () => ({
  StructureThumbnail: (p: { smiles: string }) => <div data-testid="structure">{p.smiles}</div>,
}));
const plots: P[] = [];
const downloadImage = vi.fn();
vi.mock("@/shared/lib/plotly", () => ({
  getPlotlyGlobal: () => ({ downloadImage }),
  Plot: (p: P) => {
    plots.push(p);
    return (
      <button
        type="button"
        data-testid="plot"
        onClick={() => p.onClick?.({ points: [{ customdata: "b" }] })}
      />
    );
  },
}));

import { selectedOutline } from "../lib/shift-figure";
import { ShiftPlot } from "./shift-plot";

const rows = [
  { wellId: "a", label: "A", deltaTm: -5 },
  { wellId: "b", label: "B", deltaTm: 0.5 },
  { wellId: "c", label: "C", deltaTm: 3 },
];
const last = () => plots[plots.length - 1];
const OUTSIDE = { kind: "outside", low: -2, high: 2 } as const;
const show = (selected: string[] = [], onSelect = () => {}) =>
  render(
    <ShiftPlot
      rows={rows}
      hits={new Set(["a", "c"])}
      band={OUTSIDE}
      selected={new Set(selected)}
      onSelect={onSelect}
    />,
  );

beforeEach(() => {
  plots.length = 0;
});

describe("ShiftPlot", () => {
  it("ranks by ΔTm with the rule's band and zero line", () => {
    show();
    const { data, layout } = last();
    expect(data[0].x).toEqual([-5, 0.5, 3]);
    expect(data[0].y).toEqual(["A", "B", "C"]);
    expect(data[0].orientation).toBe("h");
    expect(layout.height).toBe(240);
    const band = layout.shapes.find((s: any) => s.type === "rect");
    expect([band.x0, band.x1]).toEqual([-2, 2]);
    expect(layout.shapes.some((s: any) => s.type === "line" && s.x0 === 0)).toBe(true);
    const text = layout.annotations.map((a: any) => a.text);
    expect(text).toEqual(["outside −2 to 2 °C is a hit", "ΔTm = 0 (reference)"]);
    // One button saves the figure as SVG on white with dark ink, whatever the theme.
    const [[save]] = last().config.modeBarButtons as {
      name: string;
      click: (gd: unknown) => void;
    }[][];
    expect(save.name).toBe("Save as SVG");
    save.click({
      data: [{ x: [1] }],
      layout: { font: { size: 12 } },
      clientWidth: 640,
      clientHeight: 300,
    });
    expect(downloadImage).toHaveBeenCalledWith(
      {
        data: [{ x: [1] }],
        layout: {
          font: { size: 12, color: "#707372" },
          paper_bgcolor: "#ffffff",
          plot_bgcolor: "#ffffff",
        },
      },
      { format: "svg", width: 640, height: 300, filename: "shift-plot" },
    );
  });

  it("colours match the grid tint and the selected point is enlarged", () => {
    show(["c"]);
    const m = last().data[0].marker;
    expect(m.color[0]).not.toBe(m.color[1]);
    expect(m.color[1]).not.toBe(m.color[2]);
    expect(m.color[0]).not.toBe(m.color[2]);
    expect(m.size).toEqual([8, 8, 11]);
    // The ring is light ink on the (default) dark surface, dark ink on the light one.
    expect(m.line.color).toBe(selectedOutline(undefined));
    expect(selectedOutline("dark")).toBe("#f1f5f9");
    expect(selectedOutline("light")).toBe("#111827");
  });

  it("colours hits by sign and everything else neutral", () => {
    render(
      <ShiftPlot
        rows={[
          { wellId: "a", label: "A", deltaTm: 1.5 },
          { wellId: "b", label: "B", deltaTm: 3 },
          { wellId: "c", label: "C", deltaTm: -3 },
        ]}
        hits={new Set(["a", "c"])}
        band={null}
        selected={new Set()}
        onSelect={() => {}}
      />,
    );
    const c = last().data[0].marker.color;
    expect(c[0]).not.toBe(c[1]); // a hit at +1.5 is coloured; b at +3 is no hit
    expect(c[0]).not.toBe(c[2]); // up and down differ
  });

  it("a one-sided rule draws a dashed line; no rule draws only the zero line", () => {
    render(
      <ShiftPlot
        rows={rows}
        hits={new Set()}
        band={{ kind: "line", at: 2 }}
        selected={new Set()}
        onSelect={() => {}}
      />,
    );
    const line = last().layout.shapes.find((s: any) => s.x0 === 2);
    expect(line).toMatchObject({ type: "line", x1: 2, line: { dash: "dash" } });
    expect(last().layout.shapes.some((s: any) => s.type === "rect")).toBe(false);
    render(
      <ShiftPlot
        rows={rows}
        hits={new Set()}
        band={null}
        selected={new Set()}
        onSelect={() => {}}
      />,
    );
    expect(last().layout.shapes).toHaveLength(1);
    expect(last().layout.annotations.map((a: any) => a.text)).toEqual(["ΔTm = 0 (reference)"]);
  });

  it("the hover text shows a ΔTm beside a limit of the rule to two decimals", () => {
    render(
      <ShiftPlot
        rows={[
          { wellId: "a", label: "A", deltaTm: -2.02 },
          { wellId: "b", label: "B", deltaTm: 0.5 },
          { wellId: "c", label: "C", deltaTm: 2 },
        ]}
        hits={new Set(["a"])}
        band={OUTSIDE}
        limits={[-2, 2]}
        selected={new Set()}
        onSelect={() => {}}
      />,
    );
    expect(last().data[0].text).toEqual(["−2.02", "+0.5", "+2.0"]);
    // Plotly's own label is off: the card beside the cursor says it, with the structure.
    expect(last().data[0].hoverinfo).toBe("none");
    // Without limits, one decimal as before.
    show();
    expect(last().data[0].text).toEqual(["−5.0", "+0.5", "+3.0"]);
  });

  it("hovering a point shows its name, ΔTm and structure beside the cursor; leaving hides it", () => {
    render(
      <ShiftPlot
        rows={[
          { wellId: "a", label: "CC-1 · SACC-0455096", deltaTm: 3.04, smiles: "CCO" },
          { wellId: "b", label: "Lipid X", deltaTm: -1 },
        ]}
        hits={new Set()}
        band={null}
        selected={new Set()}
        onSelect={() => {}}
      />,
    );
    expect(screen.queryByRole("tooltip")).toBeNull();
    const hover = (id: string) =>
      act(() =>
        last().onHover?.({ event: { clientX: 40, clientY: 50 }, points: [{ customdata: id }] }),
      );
    hover("a");
    const card = screen.getByRole("tooltip");
    expect(card).toHaveTextContent("CC-1 · SACC-0455096");
    expect(card).toHaveTextContent("ΔTm +3.0 °C");
    expect(screen.getByTestId("structure")).toHaveTextContent("CCO");
    expect(card.style.left).toBe("52px");
    expect(card.style.top).toBe("62px");
    // A sample without a registered structure: the card, and no drawing.
    hover("b");
    expect(screen.getByRole("tooltip")).toHaveTextContent("Lipid X");
    expect(screen.queryByTestId("structure")).toBeNull();
    act(() => last().onUnhover?.());
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("click selects the position", () => {
    const onSelect = vi.fn();
    const { getByTestId } = show([], onSelect);
    fireEvent.click(getByTestId("plot"));
    expect(onSelect).toHaveBeenCalledWith("b");
  });

  it("scrolls beyond 60 rows, not before", () => {
    const many = (n: number) =>
      Array.from({ length: n }, (_, i) => ({ wellId: `w${i}`, label: `L${i}`, deltaTm: i }));
    const view = (n: number) =>
      render(
        <ShiftPlot
          rows={many(n)}
          hits={new Set()}
          band={null}
          selected={new Set()}
          onSelect={() => {}}
        />,
      );
    const a = view(61);
    expect(a.getByTestId("plot").parentElement).toHaveStyle({
      maxHeight: "560px",
      overflowY: "auto",
    });
    a.unmount();
    const b = view(20);
    expect(b.getByTestId("plot").parentElement?.style.overflowY ?? "").toBe("");
  });
});
