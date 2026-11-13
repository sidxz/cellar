import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CurvePositions } from "../../types";

let positions: { data?: CurvePositions; isLoading?: boolean; error?: unknown };
const positionCalls: unknown[][] = [];
vi.mock("../../hooks/use-curve-positions", () => ({
  useCurvePositions: (...args: unknown[]) => {
    positionCalls.push(args);
    return positions;
  },
}));

const viewerProps: Record<string, unknown>[] = [];
vi.mock("../multi-run-curves", () => ({
  MultiRunCurves: (props: Record<string, unknown>) => {
    viewerProps.push(props);
    return <div data-testid="viewer" />;
  },
}));

vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useWorkspaceMembers: () => ({ data: [{ user_id: "u1", name: "Ada Lovelace" }] }),
}));

import { CurvesTab } from "./curves-tab";

const holder = { kind: "k", rows: 1, columns: 3, label: "Holder of 3" };

function run(runId: string, runDate: string, over: Record<string, unknown> = {}) {
  return {
    run_id: runId,
    run_date: runDate,
    operator: "u1",
    status: "completed",
    notes: null,
    holder,
    channels: [],
    position_count: 3,
    ...over,
  };
}

const found = (runs: ReturnType<typeof run>[]): CurvePositions =>
  ({ protocol_id: "p1", dose_unit: "uM", runs, positions: [] }) as unknown as CurvePositions;

function Host({ initial = [] as string[] }) {
  const [ids, setIds] = useState<string[]>(initial);
  return <CurvesTab protocolId="p1-0000-0000" runIds={ids} onRunIdsChange={setIds} />;
}

const rows = () =>
  within(screen.getByRole("list", { name: "Runs with traces" })).getAllByRole("listitem");

describe("CurvesTab", () => {
  beforeEach(() => {
    positionCalls.length = 0;
    viewerProps.length = 0;
    positions = {
      data: found([
        run("r3", "2026-11-05", { status: "draft", position_count: 12 }),
        run("r2", "2026-11-04"),
        run("r1", "2026-11-03"),
      ]),
    };
  });

  it("lists the runs that have curves, newest first, none chosen, and no viewer yet", () => {
    render(<Host />);
    expect(positionCalls[0]).toEqual(["p1-0000-0000", {}]);
    const items = rows();
    expect(items.map((r) => r.textContent)).toEqual([
      expect.stringContaining("2026-11-05"),
      expect.stringContaining("2026-11-04"),
      expect.stringContaining("2026-11-03"),
    ]);
    expect(items[0]).toHaveTextContent("Ada Lovelace");
    expect(items[0]).toHaveTextContent("Draft");
    expect(items[0]).toHaveTextContent("12 positions");
    for (const box of screen.getAllByRole("checkbox")) {
      expect(box).toHaveAttribute("aria-checked", "false");
    }
    expect(screen.getByText("Choose runs above to see their traces")).toBeInTheDocument();
    expect(screen.queryByTestId("viewer")).not.toBeInTheDocument();
  });

  it("tells two runs on the same date apart", () => {
    positions = {
      data: found([
        run("r2", "2026-11-04", { notes: "Second plate of the day" }),
        run("aaaabbbb-0000", "2026-11-04"),
        run("r1", "2026-11-03", { notes: "Alone on its date" }),
      ]),
    };
    render(<Host />);
    const [a, b, c] = rows();
    expect(a).toHaveTextContent("Second plate of the day");
    expect(b).toHaveTextContent("Run aaaabbbb");
    expect(c).not.toHaveTextContent("Alone on its date");
  });

  it("renders the viewer for the chosen runs, coloured by run", () => {
    render(<Host />);
    fireEvent.click(screen.getByRole("checkbox", { name: /2026-11-04/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /2026-11-05/ }));
    const props = viewerProps.at(-1);
    expect(props).toMatchObject({
      protocolId: "p1-0000-0000",
      filter: { runIds: ["r2", "r3"] },
      initial: { select: "none", showReferences: false, colour: { mode: "group", groupBy: "run" } },
      exportName: "protocol-traces-p1-0000-",
    });
    expect(screen.queryByText("Choose runs above to see their traces")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.queryByTestId("viewer")).not.toBeInTheDocument();
  });

  it("disables the ninth run and states the limit", () => {
    const nine = Array.from({ length: 9 }, (_, i) => run(`r${i + 1}`, `2026-10-0${9 - i}`));
    positions = { data: found(nine) };
    render(<Host initial={nine.slice(0, 8).map((r) => r.run_id)} />);
    expect(screen.getByText("At most 8 runs at once")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /2026-10-01/ })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: /2026-10-09/ })).not.toBeDisabled();
  });

  it("shows a skeleton while loading and a line when the runs cannot be loaded", () => {
    positions = { isLoading: true };
    const { unmount } = render(<Host />);
    expect(screen.getByTestId("curves-tab-loading")).toBeInTheDocument();
    unmount();
    positions = { error: new Error("boom") };
    render(<Host />);
    expect(screen.getByText("Could not load the runs.")).toBeInTheDocument();
  });
});
