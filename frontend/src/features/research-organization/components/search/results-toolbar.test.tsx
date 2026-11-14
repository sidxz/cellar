import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../lib/use-aggregation-mode", async (orig) => ({
  ...(await orig<typeof import("../../lib/use-aggregation-mode")>()),
  useAggregationMode: () => ({ mode: "latest", setMode: vi.fn() }),
}));

import { useReportConfig } from "../../hooks/use-report-config";
import { ResultsViewControls } from "./results-toolbar";

const controls = (canOverlay: boolean) => (
  <ResultsViewControls onCustomizeReport={() => {}} hasAssays canOverlay={canOverlay} />
);

beforeEach(() => useReportConfig.getState().loadFromSavedSearch(null));

describe("display switch", () => {
  it("offers Compact and Detailed only, Detailed even without curves", () => {
    render(<ResultsViewControls onCustomizeReport={() => {}} hasAssays />);
    const display = screen.getByRole("group", { name: "Results display" });
    expect([...display.querySelectorAll("button")].map((b) => b.textContent)).toEqual([
      "Compact",
      "Detailed",
    ]);
    const detailed = screen.getByRole("button", { name: "Detailed" });
    expect(detailed).toBeEnabled();
    expect(detailed).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Compact" }));
    expect(useReportConfig.getState().config).toMatchObject({
      displayPreset: "compact",
      imageSize: "small",
    });
  });
});

describe("plot layout switch", () => {
  it("offers separate and overlaid plots for split curves", () => {
    render(controls(true));
    expect(screen.getByRole("button", { name: "Separate" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "Overlay" }));
    expect(useReportConfig.getState().config.plotLayout).toBe("overlay");
  });

  it("is hidden when nothing can be overlaid", () => {
    render(controls(false));
    expect(screen.queryByRole("button", { name: "Overlay" })).toBeNull();
  });

  it("is hidden outside the Detailed display", () => {
    useReportConfig.getState().updateConfig({ displayPreset: "compact" });
    render(controls(true));
    expect(screen.queryByRole("button", { name: "Overlay" })).toBeNull();
  });
});
