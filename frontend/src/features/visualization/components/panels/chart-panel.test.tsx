import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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
  StructureThumbnail: ({ smiles }: { smiles: string }) => <span>structure {smiles}</span>,
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

describe("ChartPanel", () => {
  it("shows a box point's compound card, and a box's median and quartiles over the box", () => {
    render(
      <WorkbenchProvider initialPanels={[box]}>
        <ChartPanel panel={box} ds={ds} />
      </WorkbenchProvider>,
    );
    hover({ points: [{ customdata: 1 }], event: { clientX: 1, clientY: 1 } });
    expect(screen.getByRole("tooltip")).toHaveTextContent("CEL-2");
    expect(screen.getByText("structure CCO")).toBeInTheDocument();

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
});
