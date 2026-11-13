import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Protocol, Run } from "../../types";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useWorkspaceMembers: () => ({ data: [] }),
}));
vi.mock("@/features/workspace-config/hooks/use-organizations", () => ({
  useOrganizations: () => ({ data: [] }),
}));

const runs = [
  { id: "r1", run_date: "2026-11-05", operator: "u1", status: "completed" },
  { id: "r2", run_date: "2026-11-04", operator: "u1", status: "draft" },
  { id: "r3", run_date: "2026-11-03", operator: "u1", status: "approved" },
] as unknown as Run[];
vi.mock("../../hooks/use-runs", () => ({
  useRunsByProtocol: () => ({ data: runs, isLoading: false }),
}));

const positionCalls: unknown[][] = [];
vi.mock("../../hooks/use-curve-positions", () => ({
  useCurvePositions: (...args: unknown[]) => {
    positionCalls.push(args);
    return { data: { runs: [{ run_id: "r1" }, { run_id: "r3" }], positions: [] } };
  },
}));

// AG Grid needs a layout engine; the stub shows the toolbar and lets a test
// tick rows the way the grid's checkbox column reports them.
const gridProps: Record<string, unknown>[] = [];
vi.mock("@/shared/components/data-grid/data-grid", () => ({
  DataGrid: (props: {
    rowData: Run[];
    toolbarActions?: ReactNode;
    onSelectionChanged?: (e: { api: { getSelectedRows: () => Run[] } }) => void;
    onRowClick?: (run: Run) => void;
  }) => {
    gridProps.push(props as unknown as Record<string, unknown>);
    const tick = (ids: string[]) =>
      props.onSelectionChanged?.({
        api: { getSelectedRows: () => props.rowData.filter((r) => ids.includes(r.id)) },
      });
    return (
      <div>
        <div data-testid="toolbar">{props.toolbarActions}</div>
        <button type="button" onClick={() => tick(["r1", "r2", "r3"])}>
          tick three
        </button>
        <button type="button" onClick={() => tick(["r2"])}>
          tick r2
        </button>
        <button type="button" onClick={() => props.onRowClick?.(props.rowData[0])}>
          open first row
        </button>
      </div>
    );
  },
}));

import { RunsTab } from "./runs-tab";

const protocol = (has_measured_curves: boolean | null) =>
  ({ id: "p1", condition_definitions: [], has_measured_curves }) as unknown as Protocol;

describe("RunsTab Compare curves", () => {
  beforeEach(() => {
    push.mockClear();
    positionCalls.length = 0;
    gridProps.length = 0;
  });

  it("shows the count beside Compare curves, not inside it", () => {
    const onCompare = vi.fn();
    render(<RunsTab protocol={protocol(true)} protocolId="p1" onCompareCurves={onCompare} />);
    expect(gridProps.at(-1)).toMatchObject({ enableMultiSelect: true });

    const button = screen.getByRole("button", { name: "Compare curves" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Select runs that have curves");
    expect(screen.getByText("0 selected")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "tick three" }));
    expect(screen.getByText("3 selected")).toBeInTheDocument();
    expect(button).toHaveTextContent(/^Compare curves$/);
    expect(button).not.toBeDisabled();
    expect(screen.getByText("2 of the 3 selected runs have curves")).toBeInTheDocument();

    fireEvent.click(button);
    expect(onCompare).toHaveBeenCalledWith(["r1", "r3"]);

    fireEvent.click(screen.getByRole("button", { name: "tick r2" }));
    expect(screen.getByRole("button", { name: "Compare curves" })).toBeDisabled();
  });

  it("keeps a row click opening the run", () => {
    render(<RunsTab protocol={protocol(true)} protocolId="p1" onCompareCurves={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "open first row" }));
    expect(push).toHaveBeenCalledWith("/assays/runs/r1");
  });

  it.each([false, null])(
    "offers no Compare curves on a protocol without measured curves (%s)",
    (flag) => {
      render(<RunsTab protocol={protocol(flag)} protocolId="p1" onCompareCurves={vi.fn()} />);
      expect(screen.queryByRole("button", { name: "Compare curves" })).not.toBeInTheDocument();
      expect(screen.queryByText(/selected/)).not.toBeInTheDocument();
      // Nothing asked of the curves endpoint.
      expect(positionCalls.every((c) => c[2] === false)).toBe(true);
    },
  );
});
