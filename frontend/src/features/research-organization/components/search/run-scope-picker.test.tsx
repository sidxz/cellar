import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { RunScope } from "../../types";
import { RunScopePicker } from "./run-scope-picker";

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

vi.mock("@/features/screening-assay/hooks/use-runs", () => ({
  useRunsByProtocol: () => ({ data: [], isLoading: false }),
}));
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
