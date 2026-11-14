import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { Run } from "@/features/screening-assay/types";
import type { RunScope } from "../../types";
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

// One mode per wire-shape variant. Tests assert the contract (trigger stays
// a single short label) for every supported mode, so any future label or
// description text change is automatically picked up — there's no hardcoded
// copy to chase.
const MODES_TO_TEST: RunScope[] = [
  { mode: "any" },
  { mode: "all" },
  { mode: "latest" },
  { mode: "specific", run_ids: ["00000000-0000-0000-0000-000000000001"] },
  { mode: "past_n_days", days: 30 },
  { mode: "date_range" },
];

describe("RunScopePicker — trigger contract", () => {
  it("trigger never collapses the menu-item description into its own row", () => {
    // Regression guard for the Radix ItemText contract: shadcn's
    // auto-wrapping <SelectItem> puts every child into ItemText, which
    // <SelectValue /> reads to populate the trigger. If anyone reverts
    // <ScopeOption> back to <SelectItem>, the trigger would silently
    // start rendering the description below the label. The labels are
    // ~one word; the descriptions are full sentences — a length bound
    // catches the regression without hardcoding any copy.
    for (const value of MODES_TO_TEST) {
      const { unmount } = render(
        <RunScopePicker protocolId="p1" value={value} onChange={vi.fn()} />,
      );
      const text = screen.getByRole("combobox").textContent ?? "";
      expect(text.trim().length).toBeLessThan(30);
      unmount();
    }
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
    const latest = screen.getByRole("option", { name: /Latest run/ });
    expect(latest).toHaveAttribute("data-disabled");
    expect(latest).toHaveTextContent("Latest run picks a single run.");
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
