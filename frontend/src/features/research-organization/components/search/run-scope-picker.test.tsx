import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { Run } from "@/features/screening-assay/types";
import { RunScopePicker, differingConditionKeys } from "./run-scope-picker";

// Radix Select + the SpecificRunPicker's Popover open via portals that need
// scrollIntoView + hasPointerCapture polyfills in jsdom.
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = vi.fn();
  }
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = vi.fn(() => false);
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = vi.fn();
  }
});

const runsMock = vi.hoisted(() => ({ data: [] as unknown[] }));
vi.mock("@/features/screening-assay/hooks/use-runs", () => ({
  useRunsByProtocol: () => ({ data: runsMock.data, isLoading: false }),
}));
beforeEach(() => {
  runsMock.data = [];
});

function run(overrides: Partial<Run>): Run {
  return {
    id: "r",
    run_date: "2026-11-01",
    created_at: "2026-11-14T00:04:00Z",
    operator: "u1",
    status: "approved",
    is_locked: false,
    plate_count: 1,
    molecule_count: 40,
    plate_barcodes: [],
    conditions: null,
    ...overrides,
  } as Run;
}
vi.mock("@/shared/hooks/use-workspace-members", () => ({
  useWorkspaceMembers: () => ({ data: [] }),
}));

describe("RunScopePicker options", () => {
  it.each([
    ["Any run", undefined],
    ["Every run", { mode: "all" }],
    ["Latest by run date", { mode: "latest" }],
    ["Last N days", { mode: "past_n_days", days: 30 }],
    ["Date range", { mode: "date_range" }],
    ["Specific runs", { mode: "specific", run_ids: [] }],
  ])("choosing %s emits its scope", (label, scope) => {
    const onChange = vi.fn();
    // Start from a different scope so the choice is a change.
    const start = label === "Latest by run date" ? undefined : { mode: "latest" as const };
    render(<RunScopePicker protocolId="p1" value={start} onChange={onChange} />);
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByRole("option", { name: label }));
    expect(onChange).toHaveBeenCalledExactlyOnceWith(scope);
  });
});

describe("RunScopePicker — Latest run under a condition split", () => {
  it("disables Latest run and says why", () => {
    render(
      <RunScopePicker
        protocolId="p1"
        value={undefined}
        onChange={vi.fn()}
        latestDisabledReason="Latest run picks a single run."
      />,
    );
    fireEvent.click(screen.getByRole("combobox"));
    const latest = screen.getByRole("option", { name: "Latest by run date" });
    expect(latest).toHaveAttribute("data-disabled");
    expect(latest).toHaveAccessibleDescription("Latest run picks a single run.");
  });
});

describe("RunScopePicker — specific runs", () => {
  const low = run({
    id: "r1",
    run_date: "2026-11-01",
    conditions: { "ATP Concentration": "1 mM", Temperature: "25 C" },
    notes: "low ATP arm",
  });
  const high = run({
    id: "r2",
    run_date: "2026-11-10",
    status: "completed",
    conditions: { "ATP Concentration": "10 mM", Temperature: "25 C" },
    notes: "high ATP arm",
  });

  it("opens the run list on arrival, newest experiment first, showing what sets runs apart", () => {
    runsMock.data = [low, high];
    render(
      <RunScopePicker
        protocolId="p1"
        value={{ mode: "specific", run_ids: [] }}
        onChange={vi.fn()}
      />,
    );
    const [first, second] = screen.getAllByRole("option");
    expect(first).toHaveTextContent("2026-11-10");
    expect(first).toHaveTextContent("ATP Concentration:10 mM");
    expect(first).toHaveTextContent("high ATP arm");
    expect(first).toHaveTextContent("Completed");
    expect(second).toHaveTextContent("2026-11-01");
    expect(second).not.toHaveTextContent("Approved");
  });

  it("flags an empty pick only after the run list is closed", () => {
    runsMock.data = [low];
    render(
      <RunScopePicker
        protocolId="p1"
        value={{ mode: "specific", run_ids: [] }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.queryByText("Pick at least one run.")).toBeNull();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(screen.getByText("Pick at least one run.")).toBeInTheDocument();
  });
});

describe("differingConditionKeys", () => {
  it("keeps the conditions that differ between runs, including one a run lacks", () => {
    const keys = differingConditionKeys([
      run({ conditions: { ATP: "1 mM", Temp: "25 C", Strain: "H37Rv" } }),
      run({ conditions: { ATP: "10 mM", Temp: "25 C" } }),
    ]);
    expect([...keys].sort()).toEqual(["ATP", "Strain"]);
  });
});
