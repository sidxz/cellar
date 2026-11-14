import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../lib/use-aggregation-mode", async (orig) => ({
  ...(await orig<typeof import("../../lib/use-aggregation-mode")>()),
  useAggregationMode: () => ({ mode: "latest", setMode: vi.fn() }),
}));

import { useReportConfig } from "../../hooks/use-report-config";
import { ResultsViewControls } from "./results-toolbar";

const controls = (canOverlay: boolean) => (
  <ResultsViewControls onCustomizeReport={() => {}} hasAssays hasCurves canOverlay={canOverlay} />
);

describe("plot layout switch", () => {
  beforeEach(() => {
    useReportConfig.getState().loadFromSavedSearch(null);
    useReportConfig.getState().updateConfig({ displayPreset: "curves" });
  });

  it("offers side by side and overlaid for split curves", () => {
    render(controls(true));
    expect(screen.getByRole("button", { name: /Side by side/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: /Overlaid/ }));
    expect(useReportConfig.getState().config.plotLayout).toBe("overlay");
  });

  it("is hidden when nothing can be overlaid", () => {
    render(controls(false));
    expect(screen.queryByRole("button", { name: /Overlaid/ })).toBeNull();
  });

  it("is hidden outside the Curves display", () => {
    useReportConfig.getState().updateConfig({ displayPreset: "compact" });
    render(controls(true));
    expect(screen.queryByRole("button", { name: /Overlaid/ })).toBeNull();
  });
});
