import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CurvePositions } from "../types";
import type { CurveViewerProps } from "./curve-viewer";

const viewerProps: CurveViewerProps[] = [];
vi.mock("./curve-viewer", () => ({
  CurveViewer: (props: CurveViewerProps) => {
    viewerProps.push(props);
    return <div data-testid="viewer" />;
  },
}));

let positions: { data?: CurvePositions; isLoading?: boolean; error?: unknown };
const positionCalls: unknown[][] = [];
vi.mock("../hooks/use-curve-positions", () => ({
  useCurvePositions: (...args: unknown[]) => {
    positionCalls.push(args);
    return positions;
  },
}));

const curveCalls: Array<[readonly string[], unknown]> = [];
vi.mock("../hooks/use-curves-for-positions", () => ({
  useCurvesForPositions: (ids: readonly string[], params: unknown) => {
    curveCalls.push([ids, params]);
    return {
      curves: new Map(),
      window: null,
      pending: false,
      failed: false,
      tooMany: false,
      retry: vi.fn(),
    };
  },
}));

import { MultiRunCurves } from "./multi-run-curves";

const holder = { kind: "cassette", rows: 1, columns: 3, label: "Holder of 3" };

function run(runId: string, status: string) {
  return {
    run_id: runId,
    run_date: "2026-11-03",
    operator: "u1",
    status,
    notes: null,
    holder,
    channels: [{ key: "a", label: "Signal A", x_unit: "°C", y_unit: null, x_label: null }],
    position_count: 3,
  };
}

function at(runId: string, column: number, wellType: string, moleculeId: string | null) {
  return {
    well_id: `${runId}-${column}`,
    position: `A${column}`,
    row: "A",
    column,
    well_type: wellType,
    batch_id: null,
    batch_number: null,
    molecule_id: moleculeId,
    molecule_name: moleculeId && `ABC-${moleculeId}`,
    registration_number: null,
    synonyms: [],
    smiles: null,
    dose: null,
    position_label: `Position ${column}`,
    label: null,
    note: null,
    run_id: runId,
  };
}

const found: CurvePositions = {
  protocol_id: "p1",
  dose_unit: "uM",
  runs: [run("r1", "completed"), run("r2", "rejected")],
  positions: [
    at("r1", 1, "reference", null),
    at("r1", 2, "sample", "m1"),
    at("r1", 3, "sample", "m2"),
    at("r2", 1, "reference", null),
    at("r2", 2, "sample", "m1"),
  ],
};

const lastViewer = () => viewerProps.at(-1) as CurveViewerProps;
const lastCurveIds = () => curveCalls.at(-1)?.[0];

beforeEach(() => {
  viewerProps.length = 0;
  positionCalls.length = 0;
  curveCalls.length = 0;
  positions = { data: found };
});

describe("MultiRunCurves", () => {
  it("shows the empty node when every run is hidden", () => {
    render(
      <MultiRunCurves
        protocolId="p1"
        filter={{ moleculeIds: ["m1"] }}
        hideStatuses={["completed", "rejected"]}
        exportName="curves"
        empty={<p>Nothing to show</p>}
      />,
    );
    expect(screen.getByText("Nothing to show")).toBeInTheDocument();
    expect(screen.queryByTestId("viewer")).not.toBeInTheDocument();
    expect(positionCalls[0]).toEqual(["p1", { moleculeIds: ["m1"] }]);
  });

  it("selects the compounds' positions and turns the reference switch on when asked", () => {
    render(
      <MultiRunCurves
        protocolId="p1"
        filter={{ moleculeIds: ["m1"] }}
        hideStatuses={["rejected"]}
        initial={{ select: "compounds", showReferences: true }}
        exportName="curves"
        empty={null}
      />,
    );
    const v = lastViewer();
    expect([...v.selection.selected]).toEqual(["r1-2"]);
    expect(v.showReferences).toBe(true);
    expect(v.set.groups.map((g) => g.key)).toEqual(["r1"]);
  });

  it("fetches curves for the drawn positions only", () => {
    render(
      <MultiRunCurves
        protocolId="p1"
        filter={{ moleculeIds: ["m1"] }}
        initial={{ select: "compounds", showReferences: true }}
        exportName="curves"
        empty={null}
      />,
    );
    // The selected positions of both runs, then each run's reference.
    expect(lastCurveIds()).toEqual(["r1-2", "r2-2", "r1-1", "r2-1"]);
    expect(curveCalls.at(-1)?.[1]).toEqual({ channel: "a", view: "measured", window: undefined });
  });

  it("passes the initial colour mode to the viewer", () => {
    render(
      <MultiRunCurves
        protocolId="p1"
        filter={{ runIds: ["r1"] }}
        initial={{ colour: { mode: "group", groupBy: "compound" } }}
        exportName="curves"
        empty={null}
      />,
    );
    expect(lastViewer().initialColour).toEqual({ mode: "group", groupBy: "compound" });
    expect(lastViewer().selection.selected.size).toBe(0);
  });

  it("shows the API's wording when the positions cannot be loaded", () => {
    positions = {
      error: Object.assign(new Error("API error: 422 — At most 8 runs can be shown at once"), {
        body: { detail: "At most 8 runs can be shown at once" },
      }),
    };
    render(<MultiRunCurves protocolId="p1" filter={{}} exportName="curves" empty={null} />);
    expect(screen.getByText("At most 8 runs can be shown at once")).toBeInTheDocument();
  });
});
