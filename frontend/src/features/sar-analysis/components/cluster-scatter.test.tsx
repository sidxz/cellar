import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// The component uses @/shared/lib/plotly (the shared SSR-safe wrapper) rather
// than importing react-plotly.js directly. Mock the wrapper so jsdom doesn't
// try to load the browser-only Plotly bundle.
vi.mock("@/shared/lib/plotly", () => ({
  Plot: (props: any) => (
    <div
      data-testid="plotly"
      data-traces={String(props.data?.length ?? 0)}
      data-uirevision={String(props.layout?.uirevision ?? "")}
    />
  ),
}));

import { ClusterScatter } from "./cluster-scatter";

describe("ClusterScatter", () => {
  it("renders two traces (base + stars) when representatives present", () => {
    render(
      <ClusterScatter
        points={[{ moleculeId: "a", x: 0, y: 0 }]}
        clusters={[{ moleculeId: "a", clusterId: 0 }]}
        representatives={[{ moleculeId: "a", clusterId: 0 }]}
        colorMode={{ mode: "cluster" }}
        activityPic50={{}}
        scaffoldByMol={{}}
        onSelected={() => {}}
        onPointClick={() => {}}
      />,
    );
    expect(screen.getByTestId("plotly").dataset.traces).toBe("2");
  });

  it("renders one trace when no representatives picked yet", () => {
    render(
      <ClusterScatter
        points={[{ moleculeId: "a", x: 0, y: 0 }]}
        clusters={[{ moleculeId: "a", clusterId: 0 }]}
        representatives={[]}
        colorMode={{ mode: "none" }}
        activityPic50={{}}
        scaffoldByMol={{}}
        onSelected={() => {}}
        onPointClick={() => {}}
      />,
    );
    expect(screen.getByTestId("plotly").dataset.traces).toBe("1");
  });

  it("keeps uirevision stable across redraws so the lasso selection survives", () => {
    // react-plotly.js redraws on every render; a uirevision that changes (or is absent)
    // clears the selection and fires spurious deselect/empty-select events.
    const { rerender } = render(
      <ClusterScatter
        points={[{ moleculeId: "a", x: 0, y: 0 }]}
        clusters={[{ moleculeId: "a", clusterId: 0 }]}
        representatives={[]}
        colorMode={{ mode: "none" }}
        activityPic50={{}}
        scaffoldByMol={{}}
        onSelected={() => {}}
        onPointClick={() => {}}
      />,
    );
    const before = screen.getByTestId("plotly").dataset.uirevision;
    expect(before).not.toBe("");
    rerender(
      <ClusterScatter
        points={[
          { moleculeId: "a", x: 0, y: 0 },
          { moleculeId: "b", x: 1, y: 1 },
        ]}
        clusters={[
          { moleculeId: "a", clusterId: 0 },
          { moleculeId: "b", clusterId: 1 },
        ]}
        representatives={[{ moleculeId: "b", clusterId: 1 }]}
        colorMode={{ mode: "cluster" }}
        activityPic50={{}}
        scaffoldByMol={{}}
        onSelected={() => {}}
        onPointClick={() => {}}
      />,
    );
    expect(screen.getByTestId("plotly").dataset.uirevision).toBe(before);
  });
});
